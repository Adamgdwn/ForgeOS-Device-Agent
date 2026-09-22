import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import type { AuthenticationResult } from "@azure/msal-node";

const state = mkdtempSync(resolve(tmpdir(), "galaxy-remove-"));
process.env.GALAXY_STATE_DIR = state;
const { Store } = await import("../server/store.ts");
const { OneDrive } = await import("../server/onedrive.ts");
const { setMicrosoftClientId } = await import("../server/config.ts");
setMicrosoftClientId("00000000-0000-4000-8000-000000000001");
const settle = () => new Promise<void>((done) => setImmediate(done));

test("removal clears only the selected sign-in, persists across restart, and retains imported work", async () => {
  const path = resolve(state, "persistent.sqlite");
  let store = new Store(path);
  let drive = new OneDrive(store);
  try {
    for (const slot of [1, 2]) {
      store.db.prepare("UPDATE accounts SET homeId=?, username=?, status='connected' WHERE slot=?")
        .run(`identity-${slot}`, `fixture-${slot}@example.com`, slot);
      writeFileSync(resolve(state, `onedrive-${slot}.cache`), `cache-${slot}`);
    }
    const project = store.addProject({ name: "Imported notes", kind: "onedrive", path: state, description: "fixture" });
    const conversation = store.createConversation(project.id);
    writeFileSync(resolve(state, "notes.md"), "Saved assessment notes");
    store.db.prepare("INSERT INTO imports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
      .run(project.id, "notes.md", 1, "drive-1", "item-1", "version-1", "https://example.com/notes", "notes.md", "identity-1");
    const source = store.db.prepare("SELECT * FROM imports").get();
    drive.cursors.set("removed-page", { slot: 1, url: "https://graph.microsoft.com/v1.0/fixture" });
    drive.cursors.set("kept-page", { slot: 2, url: "https://graph.microsoft.com/v1.0/fixture" });
    drive.errors.set(1, "Old sign-in error");
    await drive.remove(1);
    assert.deepEqual(drive.accounts().map((a) => a.slot), [2, 3]);
    assert.equal(existsSync(resolve(state, "onedrive-1.cache")), false);
    assert.equal(readFileSync(resolve(state, "onedrive-2.cache"), "utf8"), "cache-2");
    assert.equal(drive.account(2).status, "connected");
    assert.equal(drive.account(2).homeId, "identity-2");
    assert.equal(drive.cursors.has("removed-page"), false);
    assert.equal(drive.cursors.has("kept-page"), true);
    assert.equal(drive.errors.has(1), false);
    assert.throws(() => drive.account(1), /Add this OneDrive/);
    await assert.rejects(drive.connect(1, "Removed"), /Add this OneDrive/);
    assert.deepEqual(store.db.prepare("SELECT * FROM imports").get(), source);
    assert.equal(store.conversation(conversation.id).projectId, project.id);
    assert.equal(readFileSync(resolve(state, "notes.md"), "utf8"), "Saved assessment notes");
    drive.close(); store.close();
    store = new Store(path); store.recover(); drive = new OneDrive(store);
    assert.deepEqual(drive.accounts().map((a) => a.slot), [2, 3]);
    assert.deepEqual(drive.add(), { slot: 1 });
    assert.equal(drive.account(1).status, "disconnected");
    assert.equal(drive.account(1).homeId, null);
    assert.equal(drive.account(1).username, null);
    assert.equal(drive.account(1).label, "OneDrive 1");
    assert.throws(() => drive.add(), /All three/);
  } finally { drive.close(); store.close(); }
});

for (const result of ["success", "failure"] as const) {
  test(`a late ${result} after removing a pending sign-in cannot affect a new connection`, async () => {
    const store = new Store(":memory:");
    const drive = new OneDrive(store);
    try {
      const oldApp = drive.client(3);
      let complete!: (value: AuthenticationResult | null) => void;
      let fail!: (reason: Error) => void;
      oldApp.acquireTokenByDeviceCode = () => new Promise((resolve, reject) => { complete = resolve; fail = reject; });
      await drive.connect(3, "Waiting for IT");
      const oldRequest = drive.pending.get(3)!.request;
      await drive.remove(3);
      assert.equal(oldRequest.cancel, true);
      assert.equal(drive.pending.has(3), false);
      assert.equal(drive.accounts().some((a) => a.slot === 3), false);
      drive.add();
      const newApp = drive.client(3);
      let finishNew!: (value: AuthenticationResult | null) => void;
      newApp.acquireTokenByDeviceCode = () => new Promise((resolve) => { finishNew = resolve; });
      await drive.connect(3, "New sign-in");
      const newRequest = drive.pending.get(3)!.request;
      oldRequest.deviceCodeCallback({ userCode: "OLD-CODE", verificationUri: "https://microsoft.com/devicelogin", expiresIn: 300 } as any);
      assert.equal(drive.pending.get(3)!.code, undefined, "old code cannot leak into new sign-in");
      if (result === "success") complete({ account: { homeAccountId: "old-user", username: "old@example.com" } } as AuthenticationResult);
      else fail(new Error("Old approval failed"));
      await settle();
      assert.equal(drive.pending.get(3)!.request, newRequest);
      assert.equal(drive.account(3).status, "connecting");
      assert.equal(drive.account(3).homeId, null);
      assert.equal(drive.errors.has(3), false);
      finishNew({ account: { homeAccountId: "new-user", username: "new@example.com" } } as AuthenticationResult);
      await settle();
      assert.equal(drive.account(3).homeId, "new-user");
      assert.equal(drive.pending.has(3), false);
    } finally { drive.close(); store.close(); }
  });
}

test("an old cache callback cannot recreate or overwrite credentials after removal", async () => {
  const store = new Store(":memory:");
  const drive = new OneDrive(store);
  try {
    const oldApp = drive.client(3);
    const plugin = (oldApp as any).config.cache.cachePlugin;
    const context = { cacheHasChanged: true, tokenCache: { serialize: () => "old-token-fixture" } };
    await plugin.afterCacheAccess(context);
    const path = resolve(state, "onedrive-3.cache");
    assert.equal(existsSync(path), true);
    await drive.remove(3);
    await plugin.afterCacheAccess(context);
    assert.equal(existsSync(path), false);
    drive.add(); drive.client(3);
    writeFileSync(path, "new-cache-fixture");
    await plugin.afterCacheAccess(context);
    assert.equal(readFileSync(path, "utf8"), "new-cache-fixture");
    await assert.rejects(plugin.beforeCacheAccess(context), /removed/);
  } finally { drive.close(); store.close(); }
});

test.after(() => rmSync(state, { recursive: true, force: true }));

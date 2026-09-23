import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { randomBytes, createHash } from "node:crypto";
const state = mkdtempSync(resolve(tmpdir(), "galaxy-native-pair-"));
process.env.GALAXY_STATE_DIR = state;
process.env.GALAXY_RUNTIME = "android";
process.env.GALAXY_ORIGIN = "http://localhost:4318";
const { Auth, NATIVE_TICKET_FILE } = await import("../server/auth.ts");
const { Store } = await import("../server/store.ts");
test("acknowledged recovery survives database close/reopen and rejects stale, cross-instance or invalid writes", async () => {
  const { recovery, saveRecovery } = await import("../server/recovery.ts");
  const path = resolve(state, "durable.sqlite");
  let store = new Store(path);
  const p = store.addProject({
    name: "Recovery",
    path: state,
    kind: "local",
    description: "Fixture",
  });
  const c = store.createConversation(p.id);
  const instance = store.db
    .prepare("SELECT value FROM metadata WHERE key='instanceId'")
    .get()!.value;
  const key = `${instance}:chat:${p.id}:${c.id}`;
  const value = {
    kind: "chat",
    text: "Unsent after a crash",
    attachments: ["Budget.xlsx"],
    replyStyle: "standard",
    pending: {
      id: "never-repeat",
      text: "Unsent after a crash",
      replyStyle: "standard",
      composerText: "Unsent after a crash",
      keepText: false,
      conversationId: c.id,
    },
  };
  assert.equal(saveRecovery(store, key, value, 0).revision, 1);
  store.close();
  store = new Store(path);
  try {
    assert.deepEqual(recovery(store, key), { found: true, value, revision: 1 });
    assert.throws(() => saveRecovery(store, key, null, 0), /another view/);
    assert.throws(
      () => saveRecovery(store, key, { ...value, text: "x".repeat(14001) }, 1),
      /Invalid/,
    );
    assert.throws(
      () =>
        recovery(store, key.replace(String(instance), "different-instance")),
      /Invalid/,
    );
    saveRecovery(store, key, null, 1);
    assert.deepEqual(recovery(store, key), {
      found: true,
      value: null,
      revision: 2,
    });
  } finally {
    store.close();
  }
});
test("continuity schema upgrade preserves existing exports and keeps a stable recovery namespace", async () => {
  const { DatabaseSync } = await import("node:sqlite");
  const path = resolve(state, "legacy.sqlite");
  const legacy = new DatabaseSync(path);
  legacy.exec(
    "CREATE TABLE exports (id TEXT PRIMARY KEY, conversationId TEXT NOT NULL, filename TEXT NOT NULL, format TEXT NOT NULL, hash TEXT NOT NULL, cloudState TEXT NOT NULL DEFAULT '', webUrl TEXT NOT NULL DEFAULT ''); INSERT INTO exports VALUES ('old-export','old-conversation','Earlier.md','md','original-hash','uncertain','')",
  );
  legacy.close();
  const upgraded = new Store(path);
  const instance = upgraded.db
    .prepare("SELECT value FROM metadata WHERE key='instanceId'")
    .get()!.value;
  const row = upgraded.db
    .prepare("SELECT * FROM exports WHERE id='old-export'")
    .get()!;
  assert.equal(row.hash, "original-hash");
  assert.equal(row.cloudState, "uncertain");
  assert.equal(row.deviceSavedAt, "");
  upgraded.close();
  const reopened = new Store(path);
  assert.equal(
    reopened.db
      .prepare("SELECT value FROM metadata WHERE key='instanceId'")
      .get()!.value,
    instance,
  );
  reopened.close();
});
test("native recovery consumes a short-lived local ticket once; expired and forged tickets create no session", () => {
  const store = new Store(":memory:"),
    auth = new Auth(store);
  let cookie = "";
  const response = {
    setHeader: (_: string, value: string) => {
      cookie = value;
    },
  } as any;
  const ticket = randomBytes(32).toString("base64url");
  const record = (expires: number) =>
    writeFileSync(
      NATIVE_TICKET_FILE,
      JSON.stringify({
        hash: createHash("sha256").update(ticket).digest("hex"),
        expires,
      }),
    );
  try {
    record(Date.now() + 60000);
    assert.throws(() => auth.loginNative("forged", response), /expired/);
    assert.equal(
      store.db.prepare("SELECT count(*) n FROM sessions").get()!.n,
      0,
    );
    auth.loginNative(ticket, response);
    assert.match(cookie, /HttpOnly; SameSite=Strict/);
    assert.equal(existsSync(NATIVE_TICKET_FILE), false);
    assert.throws(() => auth.loginNative(ticket, response), /expired/);
    record(Date.now() - 1);
    assert.throws(() => auth.loginNative(ticket, response), /expired/);
    assert.equal(
      store.db.prepare("SELECT count(*) n FROM sessions").get()!.n,
      1,
    );
  } finally {
    store.close();
  }
});
test.after(() => rmSync(state, { recursive: true, force: true }));

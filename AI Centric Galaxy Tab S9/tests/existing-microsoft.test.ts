import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { request } from "node:http";
import type { ExistingMicrosoft } from "../server/config.ts";

const state = mkdtempSync(resolve(tmpdir(), "galaxy-existing-"));
process.env.GALAXY_STATE_DIR = state;
process.env.GALAXY_ORIGIN = "http://localhost:4318";
const { ExistingMicrosoftClient } = await import("../server/existing-microsoft.ts");
const { setExistingMicrosoft, readSettings } = await import("../server/config.ts");
const { OneDrive } = await import("../server/onedrive.ts");
const { Store } = await import("../server/store.ts");
const { application } = await import("../server/main.ts");
const { AgentHost, CodexRpc } = await import("../server/codex.ts");
const { PAIR_FILE } = await import("../server/auth.ts");
const binding: ExistingMicrosoft = {
  cliPath: resolve(state, "cli.js"), connectionName: "connection-a",
  username: "owner@example.com", userId: "user-a", driveId: "drive-a", label: "Existing work account",
};
writeFileSync(binding.cliPath, "process.exit(1)");
const runner = async (_path: string, args: string[]) => args[0] === "connection"
  ? [{ name: binding.connectionName, connectedAs: binding.username, active: true }]
  : "fixture-token";

test("existing connection verifies profile and drive without storing tokens", async () => {
  const paths: string[] = [];
  const client = new ExistingMicrosoftClient(async (url, init) => {
    paths.push(String(url));
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer fixture-token");
    return Response.json(String(url).includes("/me/drive") ? { id: "drive-a" } :
      { id: "user-a", userPrincipalName: binding.username });
  }, runner);
  const linked = await client.inspect(binding.cliPath, binding.label);
  assert.deepEqual(linked, binding);
  setExistingMicrosoft(linked);
  assert.equal(readFileSync(resolve(state, "settings.json"), "utf8").includes("fixture-token"), false);
  assert.equal(paths.length, 2);
});

test("a changed active CLI connection is rejected before requesting credentials", async () => {
  let calls = 0;
  const client = new ExistingMicrosoftClient(async () => { throw new Error("must not request Graph"); }, async () => {
    calls++;
    return [{ name: "other", connectedAs: "other@example.com", active: true }];
  });
  await assert.rejects(client.token(binding), /active Microsoft account changed/);
  assert.equal(calls, 1);
});

test("switching account between CLI commands fails validation of the actual token", async () => {
  const client = new ExistingMicrosoftClient(async () => Response.json({ id: "different-user" }), runner);
  await assert.rejects(client.token(binding), /different identity/);
});

test("failed CLI output never appears in application errors", async () => {
  const failing = resolve(state, "failing-cli.js");
  writeFileSync(failing, 'console.error("private-fixture-credential"); process.exit(1)');
  const client = new ExistingMicrosoftClient();
  await assert.rejects(client.inspect(failing, "Fixture"), (error: Error) => {
    assert.match(error.message, /connection is unavailable/);
    assert.doesNotMatch(error.message, /private-fixture-credential/);
    return true;
  });
});

test("host browsing pins the drive, blocks writes, and unlink leaves CLI sign-in untouched", async () => {
  setExistingMicrosoft(binding);
  const store = new Store(":memory:");
  const paths: string[] = [];
  const drive = new OneDrive(store, async (url) => {
    paths.push(String(url));
    return Response.json({ value: [] });
  });
  drive.existing = new ExistingMicrosoftClient(async () => Response.json({ id: binding.userId }), runner);
  try {
    assert.equal(drive.accounts().length, 4);
    assert.equal(drive.accounts()[3].readOnly, true);
    await drive.browse(4);
    assert.ok(paths[0].startsWith("https://graph.microsoft.com/v1.0/drives/drive-a/root/children?"));
    await assert.rejects(drive.request(4, "/me/drive/root", { method: "POST" }), /browsing and importing only/);
    await assert.rejects(drive.request(4, "/drives/someone-else/root"), /does not belong/);
    await assert.rejects(drive.connect(4, "Name"), /host terminal/);
    assert.equal(paths.length, 1);
    await drive.disconnect(4);
    assert.equal(readSettings().existingMicrosoft, undefined);
    assert.equal(drive.accounts().length, 3);
  } finally { store.close(); }
});

test("HTTP host-account import retains provenance, omits download authorization and prevents save", async () => {
  setExistingMicrosoft(binding);
  const store = new Store(":memory:");
  const calls: { url: string; authorization: string | null }[] = [];
  const item = { id: "item-a", name: "notes.md", size: 14, eTag: "version-a",
    webUrl: "https://example.sharepoint.com/notes.md", parentReference: { driveId: "drive-a" } };
  const drive = new OneDrive(store, async (url, init) => {
    calls.push({ url: String(url), authorization: new Headers(init?.headers).get("Authorization") });
    if (String(url) === "https://example.sharepoint.com/download") return new Response("# Test notes\n");
    if (String(url).endsWith("/content")) return new Response(null, {
      status: 302, headers: { Location: "https://example.sharepoint.com/download" },
    });
    if (String(url).includes("/children?")) return Response.json({ value: [item] });
    return Response.json(item);
  });
  drive.existing = new ExistingMicrosoftClient(async () => Response.json({ id: binding.userId }), runner);
  const host = new AgentHost(store, (cwd) => new CodexRpc(cwd, process.execPath, [resolve("tests/fake-codex.mjs")]));
  const app = application(store, host, drive);
  app.server.listen(0, "127.0.0.1");
  await new Promise<void>((done) => app.server.once("listening", done));
  const port = (app.server.address() as { port: number }).port;
  let cookie = "";
  async function call(path: string, body?: unknown) {
    return new Promise<{ status: number; data: any }>((done, reject) => {
      const req = request({ hostname: "127.0.0.1", port, path,
        method: body === undefined ? "GET" : "POST", headers: {
          Host: "localhost:4318", Origin: "http://localhost:4318", Cookie: cookie,
          "X-Galaxy-Request": "1", "Content-Type": "application/json",
        } }, (res) => {
          const chunks: Buffer[] = [];
          if (res.headers["set-cookie"]) cookie = res.headers["set-cookie"][0].split(";")[0];
          res.on("data", (chunk) => chunks.push(chunk));
          res.on("end", () => done({ status: res.statusCode!, data: JSON.parse(Buffer.concat(chunks).toString()) }));
        });
      req.on("error", reject);
      req.end(body === undefined ? undefined : JSON.stringify(body));
    });
  }
  try {
    assert.equal((await call("/api/accounts/4/files")).status, 401);
    assert.equal((await call("/api/accounts/4/preview?item=item-a&connection=unknown")).status, 401);
    assert.equal((await call("/api/accounts/1/remove", {})).status, 401);
    assert.equal((await call("/api/accounts", {})).status, 401);
    assert.equal((await call("/api/session", { code: readFileSync(PAIR_FILE, "utf8") })).status, 200);
    assert.equal((await call("/api/settings/microsoft", { clientId: "00000000-0000-4000-8000-000000000001" })).status, 404);
    assert.equal(readSettings().microsoftClientId, undefined, "paired tablets cannot change the developer registration");
    assert.equal((await call("/api/accounts/4/files")).data.items[0].name, item.name);
    const connectionId = (await call("/api/accounts")).data.find((a: any) => a.slot === 4).connectionId;
    const cloudPreview = await call(`/api/accounts/4/preview?item=item-a&connection=${connectionId}`);
    assert.equal(cloudPreview.status, 200);
    assert.match(cloudPreview.data.text, /Test notes/);
    assert.equal(cloudPreview.data.source.originalName, item.name);
    assert.equal((await call("/api/accounts/4/preview?item=item-a&connection=stale")).status, 400);
    const result = await call("/api/collections", { name: "Host import", items: [{ slot: 4, itemId: item.id }] });
    assert.equal(result.status, 200);
    const source = store.db.prepare("SELECT * FROM imports WHERE projectId=?").get(result.data.id)!;
    assert.equal(source.homeId, "m365:drive-a:user-a");
    assert.equal(source.etag, "version-a");
    assert.equal(source.driveId, "drive-a");
    const preview = await call(`/api/projects/${result.data.id}/preview?path=${encodeURIComponent(String(source.localName))}`);
    assert.equal(preview.data.source.originalName, item.name);
    assert.match(preview.data.text, /Test notes/);
    assert.equal(calls.find((c) => c.url.endsWith("/download"))?.authorization, null);
    const beforeSave = calls.length;
    await assert.rejects(drive.save(result.data.id, result.data.path, String(source.localName)), /local draft/);
    assert.equal(calls.length, beforeSave);
    assert.equal((await call("/api/accounts/4/remove", {})).status, 200);
    assert.equal(drive.accounts().length, 3);
    assert.ok((await call(`/api/projects/${result.data.id}/preview?path=${encodeURIComponent(String(source.localName))}`)).data.source);
    assert.equal((await call("/api/accounts/1/remove", {})).status, 200);
    assert.deepEqual((await call("/api/accounts")).data.map((a: any) => a.slot), [2, 3]);
    assert.deepEqual((await call("/api/accounts", {})).data, { slot: 1 });
    assert.equal((await call("/api/accounts", {})).status, 400);
  } finally { await app.close(); }
});

test.after(() => rmSync(state, { recursive: true, force: true }));

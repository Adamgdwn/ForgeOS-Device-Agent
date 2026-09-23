import test from "node:test";
import assert from "node:assert/strict";
import { request } from "node:http";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

const state = mkdtempSync(resolve(tmpdir(), "galaxy-voice-http-"));
process.env.GALAXY_STATE_DIR = state;
process.env.GALAXY_RUNTIME = "android";
process.env.GALAXY_ORIGIN = "http://localhost:4318";
const { Store } = await import("../server/store.ts");
const { application } = await import("../server/main.ts");
const { PAIR_FILE } = await import("../server/auth.ts");

test("voice API requires pairing and returns a transcript once to its conversation", async () => {
  const store = new Store(":memory:");
  const project = store.addProject({ name: "Voice test", path: state, kind: "local", description: "Fixture" });
  const conversation = store.createConversation(project.id);
  const instance = store.db.prepare("SELECT value FROM metadata WHERE key='instanceId'").get()!.value;
  const key = `${instance}:chat:${project.id}:${conversation.id}`;
  const app = application(store);
  await new Promise<void>((done) => app.server.listen(0, "127.0.0.1", done));
  const port = (app.server.address() as { port: number }).port;
  const call = (path: string, method = "GET", data?: unknown, cookie = "", origin = true) =>
    new Promise<{ status: number; headers: Record<string, string | string[] | undefined>; body: any }>((done, reject) => {
      const req = request({ hostname: "127.0.0.1", port, path, method, headers: {
        Host: "localhost:4318", ...(cookie ? { Cookie: cookie } : {}),
        ...(method === "POST" ? { "Content-Type": "application/json", "X-Galaxy-Request": "1",
          ...(origin ? { Origin: "http://localhost:4318" } : {}) } : {}),
      } }, (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
        res.on("end", () => done({ status: res.statusCode || 0, headers: res.headers,
          body: JSON.parse(Buffer.concat(chunks).toString("utf8")) }));
      });
      req.on("error", reject);
      req.end(data === undefined ? undefined : JSON.stringify(data));
    });
  try {
    assert.equal((await call("/api/voice/start", "POST", { key, revision: 0 })).status, 401);
    const paired = await call("/api/session", "POST", { code: readFileSync(PAIR_FILE, "utf8") });
    assert.equal(paired.status, 200);
    const cookie = String(paired.headers["set-cookie"]?.[0]).split(";")[0];
    assert.equal((await call("/api/voice/start", "POST", { key, revision: 0 }, cookie, false)).status, 400);
    assert.equal((await call("/api/voice/start", "POST", { key, revision: 1 }, cookie)).status, 400);
    const started = await call("/api/voice/start", "POST", { key, revision: 0 }, cookie);
    assert.equal(started.status, 200);
    assert.equal((await call("/api/voice/next", "GET", undefined, cookie)).body.id, started.body.id);
    assert.equal((await call("/api/voice/result", "POST", {
      id: started.body.id, status: "complete", text: "Meeting notes",
    }, cookie)).status, 200);
    const transcript = (await call(`/api/voice/status?id=${started.body.id}`, "GET", undefined, cookie)).body;
    assert.deepEqual(transcript, { state: "complete", key, revision: 0, text: "Meeting notes" });
    assert.equal((await call(`/api/voice/status?id=${started.body.id}`, "GET", undefined, cookie)).body.state, "expired");
  } finally {
    await app.close();
    assert.ok(state.startsWith(resolve(tmpdir(), "galaxy-voice-http-")));
    rmSync(state, { recursive: true, force: true });
  }
});

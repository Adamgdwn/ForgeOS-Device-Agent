import test from "node:test";
import { request as httpRequest } from "node:http";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  writeFileSync,
  readFileSync,
  mkdirSync,
  rmSync,
  symlinkSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
const state = mkdtempSync(resolve(tmpdir(), "galaxy-tests-"));
process.env.GALAXY_STATE_DIR = resolve(state, "state");
process.env.GALAXY_ORIGIN = "http://localhost:4318";
const { Store, redact } = await import("../server/store.ts");
const {
  safePath,
  listFiles,
  createDraft,
  changes,
  applyLocalChange,
  readDocument,
} = await import("../server/files.ts");
const { CodexRpc, AgentHost } = await import("../server/codex.ts");
const { application } = await import("../server/main.ts");
const { PAIR_FILE } = await import("../server/auth.ts");
const { OneDrive } = await import("../server/onedrive.ts");
const { setMicrosoftClientId } = await import("../server/config.ts");
const fake = resolve("tests/fake-codex.mjs");
const waitFor = async (condition: () => boolean, timeout = 5000) => {
  const started = Date.now();
  while (!condition()) {
    if (Date.now() - started > timeout) throw new Error("Condition timed out");
    await new Promise((r) => setTimeout(r, 25));
  }
};
function fixture() {
  const root = mkdtempSync(resolve(state, "folder-"));
  writeFileSync(resolve(root, "notes.md"), "# Notes\nDate: October 15\n");
  const store = new Store(":memory:");
  const project = store.addProject({
    name: "Test folder",
    path: root,
    kind: "local",
    description: "Fixture",
  });
  const conversation = store.createConversation(project.id);
  return { root, store, project, conversation };
}
test("paths reject traversal, secrets, absolute paths, and symlink escapes", async () => {
  const f = fixture();
  writeFileSync(resolve(f.root, ".env"), "SENSITIVE");
  symlinkSync(state, resolve(f.root, "escape"));
  for (const path of [
    "../elsewhere",
    "/etc/passwd",
    ".env",
    "escape/file",
    "dir/../../elsewhere",
    "secrets.json",
    "test\\file",
  ])
    assert.throws(() => safePath(f.root, path));
  assert.deepEqual(
    listFiles(f.root).map((f) => f.name),
    ["notes.md"],
  );
  assert.match((await readDocument(f.root, "notes.md")).text, /October 15/);
  f.store.close();
});
test("draft captures current unsaved working files and detects conflicting originals", async () => {
  const f = fixture();
  const workspace = await createDraft(f.project, f.conversation.id);
  const c = f.store.update(f.conversation.id, { workspace, mode: "draft" });
  writeFileSync(resolve(workspace, "notes.md"), "# Notes\nDate: October 22\n");
  assert.equal(
    readFileSync(resolve(f.root, "notes.md"), "utf8"),
    "# Notes\nDate: October 15\n",
  );
  const diff = await changes(c, f.project);
  assert.equal(diff.length, 1);
  assert.match(diff[0].diff, /-Date: October 15/);
  assert.equal(diff[0].conflict, false);
  writeFileSync(resolve(f.root, "notes.md"), "Someone else changed this.");
  await assert.rejects(
    applyLocalChange(c, f.project, "notes.md"),
    /source changed/,
  );
  assert.equal(
    readFileSync(resolve(f.root, "notes.md"), "utf8"),
    "Someone else changed this.",
  );
  f.store.close();
});
test("reviewed text changes apply, new files work, deletes do not silently apply", async () => {
  const f = fixture(),
    workspace = await createDraft(f.project, f.conversation.id),
    c = f.store.update(f.conversation.id, { workspace, mode: "draft" });
  writeFileSync(resolve(workspace, "new.md"), "A new document");
  await applyLocalChange(c, f.project, "new.md");
  assert.equal(
    readFileSync(resolve(f.root, "new.md"), "utf8"),
    "A new document",
  );
  writeFileSync(resolve(workspace, "notes.md"), "Updated");
  await applyLocalChange(c, f.project, "notes.md");
  assert.equal(readFileSync(resolve(f.root, "notes.md"), "utf8"), "Updated");
  rmSync(resolve(workspace, "notes.md"));
  await assert.rejects(
    applyLocalChange(c, f.project, "notes.md"),
    /cannot be applied/,
  );
  f.store.close();
});
test("event cursors replay only unseen events and survive a host restart", () => {
  const db = resolve(state, "persistence.sqlite"),
    root = mkdtempSync(resolve(state, "persist-"));
  let store = new Store(db);
  const p = store.addProject({
      name: "Persist",
      path: root,
      kind: "local",
      description: "",
    }),
    c = store.createConversation(p.id);
  const first = store.event(c.id, "user", { text: "hello" });
  store.event(c.id, "item", { text: "answer" });
  store.update(c.id, { status: "running" });
  store.close();
  store = new Store(db);
  store.recover();
  const events = store.events(c.id, first.seq);
  assert.equal(events.length, 2);
  assert.equal(events[0].data.text, "answer");
  assert.equal(store.conversation(c.id).status, "interrupted");
  store.close();
});
test("known credential patterns are redacted without discarding source references", () => {
  const sample =
    "Bearer test " + "sk-" + "a".repeat(30) + " api_key=secretvalue notes.md";
  const redacted = redact(sample);
  assert.ok(!redacted.includes("a".repeat(30)));
  assert.ok(!redacted.includes("secretvalue"));
  assert.ok(redacted.includes("notes.md"));
});
test("worker uses durable idempotency, resumes a thread, and rejects ID reuse", async () => {
  const f = fixture(),
    host = new AgentHost(
      f.store,
      (cwd) => new CodexRpc(cwd, process.execPath, [fake]),
    );
  try {
    await host.submit(f.conversation.id, "message-1", "Assess");
    await waitFor(() => host.active === null);
    assert.equal(f.store.conversation(f.conversation.id).status, "complete");
    assert.equal(
      (await host.submit(f.conversation.id, "message-1", "Assess")).duplicate,
      true,
    );
    await assert.rejects(
      host.submit(f.conversation.id, "message-1", "Different"),
      /reused/,
    );
    await host.submit(f.conversation.id, "message-2", "Follow up");
    await waitFor(() => host.active === null);
    assert.equal(
      f.store.conversation(f.conversation.id).threadId,
      "thread-fixture",
    );
    assert.equal(
      f.store.events(f.conversation.id).filter((e) => e.type === "user").length,
      2,
    );
  } finally {
    await host.close();
    f.store.close();
  }
});
test("meeting requests remain read-only in a draft and retries do not create another turn", async () => {
  const f = fixture();
  f.store.update(f.conversation.id, { mode: "draft" });
  const calls: { method: string; params: any }[] = [];
  const host = new AgentHost(f.store, (cwd) => {
    const rpc = new CodexRpc(cwd, process.execPath, [fake]);
    const request = rpc.request.bind(rpc);
    rpc.request = (method, params) => {
      calls.push({ method, params });
      return request(method, params);
    };
    return rpc;
  });
  try {
    for (const style of ["quick", "brief", "explain", "standard"]) {
      await host.submit(
        f.conversation.id,
        `style-${style}`,
        "What is the date?",
        style,
      );
      await waitFor(() => host.active === null);
      const turn = calls.filter((c) => c.method === "turn/start").at(-1)!;
      assert.equal(
        turn.params.sandboxPolicy.type,
        style === "standard" ? "workspaceWrite" : "readOnly",
      );
      assert.equal(turn.params.sandboxPolicy.networkAccess, false);
      const thread = calls
        .filter((c) => c.method.startsWith("thread/"))
        .at(-1)!;
      assert.equal(
        thread.params.sandbox,
        style === "standard" ? "workspace-write" : "read-only",
      );
      const before = calls.length;
      assert.equal(
        (
          await host.submit(
            f.conversation.id,
            `style-${style}`,
            "What is the date?",
            style,
          )
        ).duplicate,
        true,
      );
      assert.equal(calls.length, before);
    }
    await assert.rejects(
      host.submit(
        f.conversation.id,
        "style-quick",
        "What is the date?",
        "brief",
      ),
      /reused/,
    );
    await assert.rejects(
      host.submit(f.conversation.id, "bad-style", "What is the date?", "write"),
      /Choose/,
    );
    assert.equal(
      f.store.events(f.conversation.id).filter((e) => e.type === "user").length,
      4,
    );
    assert.ok(
      f.store
        .events(f.conversation.id)
        .filter((e) => e.type === "user")
        .every((e) => e.data.text === "What is the date?"),
    );
  } finally {
    await host.close();
    f.store.close();
  }
});
test("stop terminates the dedicated worker process group and saves interrupted state", async () => {
  const f = fixture(),
    host = new AgentHost(
      f.store,
      (cwd) => new CodexRpc(cwd, process.execPath, [fake]),
    );
  try {
    await host.submit(f.conversation.id, "hold-1", "hold");
    await waitFor(() => existsSync(resolve(f.root, "child.pid")));
    const pid = Number(readFileSync(resolve(f.root, "child.pid"), "utf8"));
    await host.stop(f.conversation.id);
    await waitFor(() => host.active === null);
    assert.equal(f.store.conversation(f.conversation.id).status, "interrupted");
    await waitFor(() => {
      try {
        process.kill(pid, 0);
        const status = readFileSync(`/proc/${pid}/stat`, "utf8");
        return status.split(" ")[2] === "Z";
      } catch {
        return true;
      }
    });
  } finally {
    await host.close();
    f.store.close();
  }
});
test("HTTP authentication, origin, host, and local file checks are enforced", async () => {
  const rawFetch = (
    url: string,
    init: {
      method?: string;
      headers?: Record<string, string>;
      body?: string;
    } = {},
  ) =>
    new Promise<Response>((resolve, reject) => {
      const req = httpRequest(
        url,
        { method: init.method, headers: init.headers },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (c) => chunks.push(c));
          res.on("end", () =>
            resolve(
              new Response(Buffer.concat(chunks), {
                status: res.statusCode,
                headers: Object.fromEntries(
                  Object.entries(res.headers).map(([key, value]) => [
                    key,
                    Array.isArray(value) ? value.join(";") : value || "",
                  ]),
                ),
              }),
            ),
          );
        },
      );
      req.on("error", reject);
      req.end(init.body);
    });
  const f = fixture(),
    host = new AgentHost(
      f.store,
      (cwd) => new CodexRpc(cwd, process.execPath, [fake]),
    ),
    app = application(f.store, host);
  app.server.listen(0, "127.0.0.1");
  await new Promise<void>((r) => app.server.once("listening", r));
  const address = app.server.address() as { port: number },
    url = `http://127.0.0.1:${address.port}`;
  const headers: Record<string, string> = {
    Host: "localhost:4318",
    Origin: "http://localhost:4318",
    "Content-Type": "application/json",
    "X-Galaxy-Request": "1",
  };
  try {
    assert.equal(
      (await rawFetch(url + "/api/bootstrap", { headers })).status,
      401,
    );
    assert.equal(
      (
        await rawFetch(url + "/api/session", {
          method: "POST",
          headers: { ...headers, Origin: "https://evil.example" },
          body: "{}",
        })
      ).status,
      400,
    );
    assert.equal(
      (
        await rawFetch(url + "/api/session", {
          headers: { Host: "evil.example" },
        })
      ).status,
      400,
    );
    const paired = await rawFetch(url + "/api/session", {
      method: "POST",
      headers,
      body: JSON.stringify({ code: readFileSync(PAIR_FILE, "utf8") }),
    });
    assert.equal(paired.status, 200);
    const cookie = paired.headers.get("set-cookie")!;
    assert.match(cookie, /HttpOnly/);
    assert.match(cookie, /SameSite=Strict/);
    headers.Cookie = cookie.split(";")[0];
    assert.equal(
      (await rawFetch(url + "/api/bootstrap", { headers })).status,
      200,
    );
    assert.equal(
      (
        await rawFetch(
          url + `/api/projects/${f.project.id}/preview?path=..%2Foutside`,
          { headers },
        )
      ).status,
      400,
    );
    const doc = (await (
      await rawFetch(
        url + `/api/projects/${f.project.id}/preview?path=notes.md`,
        { headers },
      )
    ).json()) as { text: string };
    assert.match(doc.text, /October/);
    // Reconnecting at an up-to-date cursor must open even when no new events exist.
    // Waiting for the heartbeat would leave the tablet's composer disabled for 10s.
    await new Promise<void>((resolve, reject) => {
      const req = httpRequest(
        url +
          `/api/conversations/${f.conversation.id}/events?after=${Number.MAX_SAFE_INTEGER}`,
        { headers },
        (res) => {
          assert.equal(res.statusCode, 200);
          assert.equal(res.headers["content-type"], "text/event-stream");
          let opening = "";
          res.on("data", (chunk) => {
            opening += chunk.toString();
            if (!opening.includes("\n\n")) return;
            clearTimeout(deadline);
            res.destroy();
            try {
              assert.match(opening, /retry: 1000\n: connected\n\n/);
              resolve();
            } catch (error) {
              reject(error);
            }
          });
        },
      );
      const deadline = setTimeout(
        () => req.destroy(new Error("Idle event stream did not open promptly")),
        2000,
      );
      req.on("error", (error) => {
        clearTimeout(deadline);
        reject(error);
      });
      req.end();
    });
  } finally {
    await app.close();
  }
});
test("OneDrive requests select the account token and never forward bearer to file transfer hosts", async () => {
  const f = fixture(),
    calls: { url: string; authorization: string | null }[] = [];
  const drive = new OneDrive(f.store, async (url, init) => {
    calls.push({
      url: String(url),
      authorization: new Headers(init?.headers).get("Authorization"),
    });
    return Response.json({ value: [] });
  });
  drive.token = async (slot) => `test-account-${slot}`;
  await drive.browse(1);
  await drive.browse(2);
  await drive.browse(3);
  assert.deepEqual(
    calls.map((c) => c.authorization),
    ["Bearer test-account-1", "Bearer test-account-2", "Bearer test-account-3"],
  );
  assert.ok(
    calls.every((c) => c.url.startsWith("https://graph.microsoft.com/v1.0/")),
  );
  f.store.close();
});
test("OneDrive conflicts prevent upload and leave the draft intact", async () => {
  const f = fixture();
  f.store.db
    .prepare(
      "UPDATE accounts SET homeId='account-1', status='connected' WHERE slot=1",
    )
    .run();
  f.store.db
    .prepare("INSERT INTO imports VALUES (?,?,?,?,?,?,?,?,?)")
    .run(
      f.project.id,
      "notes.md",
      1,
      "drive",
      "item",
      "old-version",
      "https://example.sharepoint.com/document",
      "notes.md",
      "account-1",
    );
  let writes = 0;
  const drive = new OneDrive(f.store, async (_url, init) => {
    if (init?.method === "POST" || init?.method === "PUT") writes++;
    return Response.json({ eTag: "new-version" });
  });
  drive.token = async () => "fake";
  await assert.rejects(
    drive.save(f.project.id, f.root, "notes.md"),
    /original changed/,
  );
  assert.equal(writes, 0);
  assert.ok(existsSync(resolve(f.root, "notes.md")));
  f.store.close();
});
test("OneDrive follows only server-issued pagination for the matching account", async () => {
  const f = fixture(),
    drive = new OneDrive(f.store, async () =>
      Response.json({
        value: [],
        "@odata.nextLink":
          "https://graph.microsoft.com/v1.0/me/drive/root/children?$skiptoken=test",
      }),
    );
  drive.token = async () => "fake";
  const page = await drive.browse(1);
  assert.ok(page.nextCursor);
  await assert.rejects(drive.browse(2, "root", page.nextCursor), /expired/);
  await assert.rejects(
    drive.browse(1, "root", "https://evil.example"),
    /expired/,
  );
  f.store.close();
});
test("OneDrive upload checks the source version and omits Graph authorization on transfer", async () => {
  const f = fixture();
  f.store.db
    .prepare(
      "UPDATE accounts SET homeId='account-1', status='connected' WHERE slot=1",
    )
    .run();
  f.store.db
    .prepare("INSERT INTO imports VALUES (?,?,?,?,?,?,?,?,?)")
    .run(
      f.project.id,
      "notes.md",
      1,
      "drive",
      "item",
      "old",
      "https://example.sharepoint.com/document",
      "notes.md",
      "account-1",
    );
  const calls: {
    url: string;
    method: string;
    auth: string | null;
    match: string | null;
  }[] = [];
  const drive = new OneDrive(f.store, async (url, init) => {
    const h = new Headers(init?.headers);
    calls.push({
      url: String(url),
      method: init?.method || "GET",
      auth: h.get("Authorization"),
      match: h.get("If-Match"),
    });
    if (init?.method === "POST")
      return Response.json({ uploadUrl: "https://files.1drv.com/upload" });
    if (init?.method === "PUT")
      return Response.json({ eTag: "new" }, { status: 201 });
    return Response.json({ eTag: "old" });
  });
  drive.token = async () => "fixture-token";
  assert.equal(
    (await drive.save(f.project.id, f.root, "notes.md")).saved,
    true,
  );
  assert.equal(calls.find((c) => c.method === "POST")?.match, "old");
  assert.equal(calls.find((c) => c.method === "PUT")?.auth, null);
  f.store.db
    .prepare("UPDATE accounts SET homeId='different-account' WHERE slot=1")
    .run();
  await assert.rejects(
    drive.save(f.project.id, f.root, "notes.md"),
    /originally supplied/,
  );
  assert.equal(calls.length, 3);
  f.store.close();
});
test("cross-account import preserves separate files and source references", async () => {
  const f = fixture();
  for (const slot of [1, 2])
    f.store.db
      .prepare(
        "UPDATE accounts SET homeId=?,username=?,status='connected' WHERE slot=?",
      )
      .run("account-" + slot, "fixture-" + slot, slot);
  const drive = new OneDrive(f.store, async (url, init) => {
    const slot = new Headers(init?.headers).get("Authorization")?.endsWith("2")
      ? 2
      : 1;
    if (String(url).endsWith("/content"))
      return new Response("Document from account " + slot);
    return Response.json({
      id: "item",
      name: "notes.md",
      size: 30,
      eTag: "version-" + slot,
      webUrl: "https://example.sharepoint.com/" + slot,
      parentReference: { driveId: "drive-" + slot },
    });
  });
  drive.token = async (slot) => "fixture-" + slot;
  const project = await drive.collect("Across accounts", [
    { slot: 1, itemId: "item" },
    { slot: 2, itemId: "item" },
  ]);
  const sources = f.store.db
    .prepare("SELECT * FROM imports WHERE projectId=? ORDER BY slot")
    .all(project.id) as any[];
  assert.equal(sources.length, 2);
  assert.notEqual(sources[0].localName, sources[1].localName);
  assert.equal(sources[1].homeId, "account-2");
  assert.match(
    readFileSync(resolve(project.path, sources[1].localName), "utf8"),
    /account 2/,
  );
  assert.match(
    readFileSync(resolve(project.path, "SOURCE_INDEX.md"), "utf8"),
    /fixture-1/,
  );
  f.store.close();
});
test("Word and PDF fixtures expose text for assessment", async () => {
  const fixtureRoot = resolve("tests/fixtures");
  assert.match(
    (await readDocument(fixtureRoot, "sample.docx")).text,
    /Workshop date: October 22/,
  );
  assert.match(
    (await readDocument(fixtureRoot, "sample.pdf")).text,
    /Workshop date: October 22/,
  );
});
test("Microsoft configuration rejects secret-shaped or malformed values", () => {
  assert.throws(() => setMicrosoftClientId("not-an-id"), /valid Microsoft/);
});
test.after(() => {
  rmSync(state, { recursive: true, force: true });
});

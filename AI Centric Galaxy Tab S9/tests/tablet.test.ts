import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync, readFileSync } from "node:fs";
import { request } from "node:http";
import { resolve } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
const root = mkdtempSync(resolve(tmpdir(), "galaxy-tablet-test-"));
process.env.GALAXY_STATE_DIR = resolve(root, "state");
const { Store } = await import("../server/store.ts");
const { Tablet, ensureTabletWorkspace, tabletPath, shellQuote } =
  await import("../server/tablet.ts");
const { createDraft } = await import("../server/files.ts");
const { AgentHost, CodexRpc } = await import("../server/codex.ts");
const { application } = await import("../server/main.ts");
const { PAIR_FILE } = await import("../server/auth.ts");

test("Native tablet tools verify the installation identity and never fall back to ADB", async () => {
  const store = new Store(":memory:");
  let bridge = "a".repeat(64);
  let calls = 0;
  const binding = {
    serial: "native",
    model: "SM-X810",
    bridgeId: bridge,
    transport: "On-device" as const,
  };
  const tablet = new Tablet(
    store,
    async () => {
      throw Error("ADB must not run");
    },
    () => binding,
    async () => {
      calls++;
      return { model: "SM-X810", bridgeId: bridge };
    },
    true,
  );
  try {
    assert.equal((await tablet.status()).transport, "On-device");
    bridge = "b".repeat(64);
    await assert.rejects(tablet.connected(), /identity changed/);
    binding.serial = "127.0.0.1:5555";
    const before = calls;
    await assert.rejects(tablet.connected(), /Invalid on-device/);
    assert.equal(calls, before);
  } finally {
    store.close();
  }
});

function fixture() {
  const store = new Store(":memory:"),
    project = ensureTabletWorkspace(store),
    c = store.createConversation(project.id);
  const state = {
    value: "300000",
    serial: "fixture-tablet",
    connected: true,
    failAfterWrite: false,
    writes: 0,
  };
  const calls: string[] = [];
  const tablet = new Tablet(
    store,
    async (serial, args) => {
      assert.equal(serial, state.serial);
      calls.push(args.join(" "));
      if (!state.connected) throw new Error("offline");
      if (args[0] === "get-state") return Buffer.from("device\n");
      const command = args[1];
      if (command === "'getprop' 'ro.product.model'")
        return Buffer.from("SM-X810\n");
      if (command.startsWith("'settings' 'get'"))
        return Buffer.from(state.value);
      if (command.startsWith("'settings' 'put'")) {
        state.value = command.split("'").at(-2)!;
        state.writes++;
        if (state.failAfterWrite) throw new Error("lost acknowledgement");
        return Buffer.alloc(0);
      }
      if (command.startsWith("'settings' 'delete'")) {
        state.value = "null";
        state.writes++;
        return Buffer.alloc(0);
      }
      if (command.startsWith("'realpath'"))
        return Buffer.from(command.split("'")[3]);
      if (command.startsWith("'find'"))
        return Buffer.from(
          "-rw-rw----\t5\t1790000000\t/storage/emulated/0/Download/meeting.txt\0-rw-rw----\t5\t1790000000\t/storage/emulated/0/Android/private.txt\0-rw-rw----\t5\t1790000000\t/storage/emulated/0/Download/.env\0-rw-rw----\t5\t1790000000\t/storage/emulated/0/Download/credentials.json\0",
        );
      return Buffer.from("");
    },
    () => ({ serial: state.serial, model: "SM-X810" }),
  );
  return { store, project, c, state, tablet, calls };
}
const proposal = (f: ReturnType<typeof fixture>) =>
  f.tablet.propose(f.c.id, {
    setting: "screen_timeout",
    value: "600000",
    reason:
      "Keep meeting notes visible longer, at the cost of extra screen-on time.",
  });

test("System is permanent and distinct; files stay in shared storage and shell arguments stay literal", async () => {
  const f = fixture();
  try {
    assert.equal(ensureTabletWorkspace(f.store).id, f.project.id);
    assert.equal(f.store.projects().length, 1);
    await assert.rejects(createDraft(f.project, f.c.id), /System/);
    for (const path of [
      "../outside",
      "/etc/passwd",
      "Android/data/app",
      "Download/.env",
      "Download/token.key",
      "Download/credentials.json",
      "Download/x\nname",
    ])
      assert.throws(() => tabletPath(path));
    assert.equal(
      tabletPath("/sdcard/Download/Meeting notes.txt"),
      "Download/Meeting notes.txt",
    );
    const hostile = "name'$(touch " + resolve(root, "should-not-exist") + ")";
    assert.equal(
      execFileSync("sh", ["-c", "printf '%s' " + shellQuote(hostile)], {
        encoding: "utf8",
      }),
      hostile,
    );
    assert.equal(existsSync(resolve(root, "should-not-exist")), false);
    const found = await f.tablet.files("Download", "meeting");
    assert.deepEqual(
      found.files.map((r) => r.path),
      ["Download/meeting.txt"],
    );
    assert.equal(f.state.writes, 0);
  } finally {
    f.store.close();
  }
});
test("a proposal does not write; apply and undo verify exact values and repeated clicks never write twice", async () => {
  const f = fixture();
  try {
    const a = await proposal(f);
    assert.ok(a && "id" in a);
    assert.equal(f.state.writes, 0);
    assert.equal(((await proposal(f)) as any).id, a.id);
    assert.equal((await f.tablet.decide(a.id, "apply"))?.status, "applied");
    assert.equal(f.state.value, "600000");
    assert.equal(f.state.writes, 1);
    await f.tablet.decide(a.id, "apply");
    assert.equal(f.state.writes, 1);
    assert.equal((await f.tablet.decide(a.id, "undo"))?.status, "undone");
    assert.equal(f.state.value, "300000");
    assert.equal(f.state.writes, 2);
    await f.tablet.decide(a.id, "undo");
    assert.equal(f.state.writes, 2);
    await assert.rejects(f.tablet.decide(a.id, "apply"), /cannot be submitted/);
  } finally {
    f.store.close();
  }
});
test("changed settings, expired proposals, different devices and unsupported operations cannot be applied", async () => {
  for (const scenario of [
    "changed",
    "expired",
    "device",
    "decline",
    "stopped",
  ]) {
    const f = fixture();
    try {
      if (scenario === "stopped") {
        await assert.rejects(
          f.tablet.propose(
            f.c.id,
            { setting: "screen_timeout", value: "600000", reason: "test" },
            () => false,
          ),
          /stopped/,
        );
        assert.equal(f.tablet.actions(f.c.id).length, 0);
        continue;
      }
      const a = await proposal(f);
      assert.ok(a && "id" in a);
      if (scenario === "changed") f.state.value = "60000";
      if (scenario === "expired")
        f.store.db
          .prepare("UPDATE tablet_actions SET createdAt=0 WHERE id=?")
          .run(a.id);
      if (scenario === "device") f.state.serial = "another-tablet";
      if (scenario === "decline") await f.tablet.decide(a.id, "decline");
      await assert.rejects(f.tablet.decide(a.id, "apply"));
      assert.equal(f.state.writes, 0);
    } finally {
      f.store.close();
    }
  }
  const f = fixture();
  try {
    await assert.rejects(
      f.tablet.propose(f.c.id, {
        setting: "factory_reset",
        value: "1",
        reason: "bad",
      }),
    );
    await assert.rejects(
      f.tablet.propose(f.c.id, {
        setting: "screen_timeout",
        value: "1; reboot",
        reason: "bad",
      }),
    );
    const other = f.store.addProject({
      name: "Regular",
      path: root,
      kind: "local",
      description: "",
    });
    await assert.rejects(
      f.tablet.tool(
        f.store.createConversation(other.id).id,
        "tablet_snapshot",
        {},
      ),
      /System/,
    );
    f.state.connected = false;
    assert.equal((await f.tablet.status()).connected, false);
  } finally {
    f.store.close();
  }
});
test("Undo restores an absent Android override and snapshots expose verified action receipts", async () => {
  const f = fixture();
  try {
    f.state.value = "null";
    const a = await proposal(f);
    assert.ok(a && "id" in a);
    await f.tablet.decide(a.id, "apply");
    await f.tablet.decide(a.id, "undo");
    assert.equal(f.state.value, "null");
    assert.ok(f.calls.some((c) => c.includes("'settings' 'delete'")));
    const snapshot = await f.tablet.snapshot(f.c.id);
    assert.equal(snapshot.actionReceipts[0].status, "undone");
    assert.equal(snapshot.actionReceipts[0].before, "Android default");
  } finally {
    f.store.close();
  }
});
test("uncertain writes and interrupted actions cannot be automatically retried", async () => {
  const f = fixture();
  try {
    const a = await proposal(f);
    assert.ok(a && "id" in a);
    f.state.failAfterWrite = true;
    await assert.rejects(f.tablet.decide(a.id, "apply"));
    assert.equal(f.tablet.actions(f.c.id)[0].status, "uncertain");
    assert.equal(f.state.writes, 1);
    await assert.rejects(f.tablet.decide(a.id, "apply"));
    assert.equal(f.state.writes, 1);
    f.store.db
      .prepare("UPDATE tablet_actions SET status='applying' WHERE id=?")
      .run(a.id);
    f.store.recover();
    assert.equal(f.tablet.actions(f.c.id)[0].status, "uncertain");
  } finally {
    f.store.close();
  }
});
test("system worker advertises only tablet extensions, disables shell, and routes tool calls on resume", async () => {
  const f = fixture(),
    calls: { method: string; params: any }[] = [];
  const host = new AgentHost(f.store, (cwd) => {
    const rpc = new CodexRpc(cwd, process.execPath, [
      resolve("tests/fake-tablet-codex.mjs"),
    ]);
    const original = rpc.request.bind(rpc);
    rpc.request = (method, params) => {
      calls.push({ method, params });
      return original(method, params);
    };
    return rpc;
  });
  host.tablet = f.tablet;
  try {
    for (const n of [1, 2]) {
      await host.submit(f.c.id, `tablet-${n}`, "Check tablet", "quick");
      const end = Date.now() + 5000;
      while (host.active && Date.now() < end)
        await new Promise((r) => setTimeout(r, 25));
      assert.equal(host.active, null);
      assert.equal(f.store.conversation(f.c.id).status, "complete");
    }
    const starts = calls.filter((c) => c.method.startsWith("thread/"));
    assert.equal(starts[0].params.dynamicTools.length, 5);
    assert.ok(
      starts[0].params.dynamicTools.every((t: any) =>
        t.name.startsWith("tablet_"),
      ),
    );
    assert.equal(starts[1].method, "thread/resume");
    for (const c of starts) {
      assert.equal(c.params.config["features.shell_tool"], false);
      assert.equal(c.params.sandbox, "read-only");
    }
    assert.ok(
      calls
        .filter((c) => c.method === "turn/start")
        .every(
          (c) =>
            c.params.sandboxPolicy.type === "readOnly" &&
            c.params.sandboxPolicy.networkAccess === false,
        ),
    );
    assert.equal(
      f.store.events(f.c.id).filter((e) => e.type === "tablet-evidence").length,
      2,
    );
    assert.equal(f.state.writes, 0);
  } finally {
    await host.close();
    f.store.close();
  }
});
test("tablet HTTP controls require pairing and origin checks and reject document mutations in System", async () => {
  const f = fixture(),
    host = new AgentHost(f.store);
  host.tablet = f.tablet;
  const app = application(f.store, host);
  await new Promise<void>((r) => app.server.listen(0, "127.0.0.1", r));
  const port = (app.server.address() as { port: number }).port;
  let cookie = "";
  const call = (
    path: string,
    method = "GET",
    data?: unknown,
    origin = "http://localhost:4318",
  ) =>
    new Promise<{ status: number; body: any; cookie?: string }>((ok, fail) => {
      const r = request(
        {
          hostname: "127.0.0.1",
          port,
          path: "/api" + path,
          method,
          headers: {
            Host: "localhost:4318",
            Origin: origin,
            "X-Galaxy-Request": "1",
            "Content-Type": "application/json",
            Cookie: cookie,
          },
        },
        (response) => {
          let text = "";
          response.on("data", (d) => (text += d));
          response.on("end", () =>
            ok({
              status: response.statusCode!,
              body: JSON.parse(text),
              cookie: response.headers["set-cookie"]?.[0]?.split(";")[0],
            }),
          );
        },
      );
      r.on("error", fail);
      r.end(data === undefined ? undefined : JSON.stringify(data));
    });
  try {
    assert.equal((await call("/tablet/status")).status, 401);
    cookie = (
      await call("/session", "POST", {
        code: readFileSync(PAIR_FILE, "utf8").trim(),
      })
    ).cookie!;
    assert.equal((await call("/tablet/status")).body.connected, true);
    const a = await proposal(f);
    assert.ok(a && "id" in a);
    assert.notEqual(
      (
        await call(
          `/tablet/actions/${a.id}`,
          "POST",
          { decision: "apply" },
          "https://elsewhere.example",
        )
      ).status,
      200,
    );
    assert.equal(f.state.writes, 0);
    assert.equal(
      (await call(`/conversations/${f.c.id}/draft`, "POST", {})).status,
      400,
    );
    assert.equal(
      (await call(`/conversations/${f.c.id}/report`, "POST", {})).status,
      400,
    );
    assert.equal(
      (await call("/materials", "POST", { projectId: f.project.id, files: [] }))
        .status,
      400,
    );
    assert.equal(
      (await call(`/tablet/actions/${a.id}`, "POST", { decision: "apply" }))
        .body.status,
      "applied",
    );
    assert.equal(
      (await call(`/tablet/actions/${a.id}`, "POST", { decision: "undo" })).body
        .status,
      "undone",
    );
    assert.equal(f.state.value, "300000");
  } finally {
    await app.close();
  }
});
test.after(() => rmSync(root, { recursive: true, force: true }));

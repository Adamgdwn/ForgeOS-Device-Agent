import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
const root = mkdtempSync(resolve(tmpdir(), "galaxy-assistant-test-"));
process.env.GALAXY_STATE_DIR = resolve(root, "state");
const { Store } = await import("../server/store.ts");
const { Tablet } = await import("../server/tablet.ts");
const { Assistant, ensureAssistantWorkspace, normalizeBriefLinks } =
  await import("../server/assistant.ts");
const { report } = await import("../server/reports.ts");
const { newStage, installMaterials } = await import("../server/materials.ts");
const { privateWrite } = await import("../server/config.ts");
const { AgentHost, CodexRpc } = await import("../server/codex.ts");
test("Meeting brief citations resolve from Reports while literal examples stay unchanged", () => {
  const text = normalizeBriefLinks(
    "[Calendar](Sources/Outlook/screen.md)\n\n[Existing](../Sources/notes.txt)\n\n[Web](https://example.com)\n\n`[Literal](Sources/example)`",
  );
  assert.match(text, /\[Calendar\]\(\.\.\/Sources\/Outlook\/screen.md\)/);
  assert.match(text, /\[Existing\]\(\.\.\/Sources\/notes.txt\)/);
  assert.match(text, /https:\/\/example.com/);
  assert.match(text, /`\[Literal\]\(Sources\/example\)`/);
});
function fixture() {
  const store = new Store(":memory:"),
    project = ensureAssistantWorkspace(store),
    c = store.createConversation(project.id);
  const tablet = new Tablet(
    store,
    async (_serial, args) =>
      Buffer.from(args[0] === "get-state" ? "device" : "SM-X810"),
    () => ({ serial: "fixture", model: "SM-X810" }),
  );
  const calls: any[] = [];
  const assistant = new Assistant(store, tablet, async (data) => {
    calls.push(data);
    return {
      text: "Council meeting\nAgenda: infrastructure",
      warnings: ["Please sign in to Council."],
      deviceTime: "2026-09-21T22:00:00-0600",
      items: [],
      coverage: "Visible screen only",
    };
  });
  return { store, project, c, tablet, assistant, calls };
}
test("Assistant keeps conversations isolated and saves a persistent meeting folder with conflict-checked brief", async () => {
  const f = fixture();
  try {
    assert.equal(ensureAssistantWorkspace(f.store).id, f.project.id);
    const second = f.store.createConversation(f.project.id);
    assert.notEqual(second.workspace, f.c.workspace);
    const captured = await f.assistant.tool(f.c.id, "outlook_calendar", {
      dayOffset: 1,
    });
    assert.ok(captured && "sourcePath" in captured);
    assert.match(
      readFileSync(
        resolve(f.c.workspace, captured.sourcePath as string),
        "utf8",
      ),
      /Please sign in/,
    );
    const original = await f.assistant.tool(f.c.id, "meeting_sources", {});
    assert.equal((original as any).report.hash, "");
    const saved: any = await f.assistant.tool(f.c.id, "meeting_save_brief", {
      title: "Council meeting",
      text: "# Council\n\nProposed questions. Sources incomplete.",
      expectedHash: "",
    });
    const c = f.store.conversation(f.c.id);
    assert.equal(c.projectId, saved.projectId);
    assert.equal(f.store.project(c.projectId).path, c.workspace);
    assert.equal(f.store.project(c.projectId).kind, "meeting");
    assert.equal(report(f.store, c.id).exists, true);
    await assert.rejects(
      f.assistant.tool(c.id, "meeting_save_brief", {
        title: "Council",
        text: "overwrite",
        expectedHash: "",
      }),
      /changed/,
    );
    await f.assistant.tool(c.id, "meeting_save_brief", {
      title: "Council",
      text: "# Council\nRevised",
      expectedHash: saved.hash,
    });
    assert.equal(
      f.store.projects().filter((p) => p.kind === "meeting").length,
      1,
    );
    const document: any = await f.assistant.tool(c.id, "meeting_sources", {
      path: captured.sourcePath,
    });
    assert.match(document.document.text, /infrastructure/);
    await assert.rejects(
      f.assistant.tool(c.id, "meeting_sources", { path: "../../outside" }),
    );
    assert.equal(report(f.store, second.id).exists, false);
  } finally {
    await f.assistant.release(f.c.id);
    f.store.close();
  }
});
test("Assistant rejects wrong workspace, stopped work, arbitrary tools and concurrent screen actions", async () => {
  const f = fixture();
  try {
    const normal = f.store.addProject({
      name: "normal",
      path: root,
      kind: "local",
      description: "",
    });
    const c = f.store.createConversation(normal.id);
    await assert.rejects(f.assistant.tool(c.id, "outlook_read", {}), /belongs/);
    await assert.rejects(f.assistant.tool(f.c.id, "shell", {}), /Unsupported/);
    await assert.rejects(
      f.assistant.tool(f.c.id, "outlook_read", {}, () => false),
      /stopped/,
    );
    assert.equal(f.calls.length, 0);
    let finish: (value: any) => void = () => {};
    let active = true;
    f.assistant.run = async () =>
      new Promise((r) => {
        finish = r;
      });
    const pending = f.assistant.tool(f.c.id, "outlook_read", {}, () => active);
    await new Promise((r) => setTimeout(r, 0));
    await assert.rejects(
      f.assistant.tool(f.c.id, "outlook_read", {}),
      /one Outlook/,
    );
    active = false;
    finish({ text: "late screen" });
    await assert.rejects(pending, /stopped/);
    assert.equal(existsSync(resolve(f.c.workspace, "Sources")), false);
  } finally {
    f.store.close();
  }
});
test("Selected materials can be added to a saved meeting without copying onto themselves or requiring a draft baseline", async () => {
  const f = fixture();
  try {
    const saved: any = await f.assistant.tool(f.c.id, "meeting_save_brief", {
      title: "Test meeting",
      text: "# Notes",
      expectedHash: "",
    });
    const stage = newStage();
    privateWrite(resolve(stage, "notes.txt"), "Meeting facts");
    await installMaterials(f.store, stage, {
      projectId: saved.projectId,
      conversationId: f.c.id,
      name: "Test meeting",
    });
    assert.equal(report(f.store, f.c.id).text, "# Notes");
    assert.equal(
      f.store
        .events(f.c.id)
        .some((e) => e.data.text?.includes("source files added")),
      true,
    );
  } finally {
    f.store.close();
  }
});
test("Outlook reader only exposes message/event opens and refuses credentials; changed content invalidates references", () => {
  execFileSync(
    "python3",
    [
      "-m",
      "unittest",
      "discover",
      "-s",
      "tests",
      "-p",
      "outlook_reader_test.py",
    ],
    { timeout: 10000 },
  );
});
test("Assistant worker uses typed tools and disabled shell on start and resume", async () => {
  const f = fixture(),
    calls: any[] = [];
  const host = new AgentHost(f.store, (cwd) => {
    const rpc = new CodexRpc(cwd, process.execPath, [
      resolve("tests/fake-assistant-codex.mjs"),
    ]);
    const request = rpc.request.bind(rpc);
    rpc.request = (method, params) => {
      calls.push({ method, params });
      return request(method, params);
    };
    return rpc;
  });
  host.assistant = f.assistant;
  try {
    for (const id of ["first", "second"]) {
      await host.submit(f.c.id, id, "Check gathered sources", "quick");
      const end = Date.now() + 5000;
      while (host.active && Date.now() < end)
        await new Promise((r) => setTimeout(r, 25));
      assert.equal(host.active, null);
      assert.equal(f.store.conversation(f.c.id).status, "complete");
    }
    const starts = calls.filter((c) => c.method.startsWith("thread/"));
    assert.equal(starts[0].params.dynamicTools.length, 8);
    assert.equal(starts[1].method, "thread/resume");
    for (const start of starts) {
      assert.equal(start.params.config["features.shell_tool"], false);
      assert.equal(start.params.sandbox, "read-only");
    }
    assert.equal(f.calls.length, 0);
  } finally {
    await host.close();
    f.store.close();
  }
});
test.after(() => rmSync(root, { recursive: true, force: true }));

import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { tmpdir } from "node:os";

const root = mkdtempSync(resolve(tmpdir(), "galaxy-code-workspace-"));
process.env.GALAXY_STATE_DIR = resolve(root, "state");
process.env.GALAXY_RUNTIME = "android";
const { Store } = await import("../server/store.ts");
const { createCodeWorkspace } = await import("../server/materials.ts");
const { WorkspaceTools } = await import("../server/workspace-tools.ts");
const { AgentHost } = await import("../server/codex.ts");
const { validateWorkspaceCommand } = await import("../server/workspace-command.ts");

test("code workspace edits are direct, hash-checked and confined to visible text paths", async () => {
  const store = new Store(":memory:");
  try {
    const project = createCodeWorkspace(store, "My code");
    const conversation = store.createConversation(project.id);
    const tools = new WorkspaceTools(store);
    writeFileSync(resolve(project.path, "main.ts"), "export const answer = 1;\n");
    const read: any = await tools.tool(conversation.id, "workspace_read", { path: "main.ts" });
    const saved: any = await tools.tool(conversation.id, "workspace_edit", {
      path: "main.ts", text: "export const answer = 2;\n", expectedHash: read.hash,
    });
    assert.match(saved.diff, /-export const answer = 1/);
    assert.match(saved.diff, /\+export const answer = 2/);
    assert.equal(readFileSync(resolve(project.path, "main.ts"), "utf8"), "export const answer = 2;\n");
    await assert.rejects(tools.tool(conversation.id, "workspace_edit", {
      path: "main.ts", text: "stale", expectedHash: read.hash,
    }), /changed/);
    for (const path of ["../outside.ts", ".env", "secrets.json"])
      await assert.rejects(tools.tool(conversation.id, "workspace_edit", {
        path, text: "bad", expectedHash: "",
      }));
    await assert.rejects(tools.tool(conversation.id, "workspace_edit", {
      path: "new.ts", text: "no", expectedHash: "",
    }, () => true, false), /read-only/);
    const created: any = await tools.tool(conversation.id, "workspace_edit", {
      path: "new.ts", text: "export {};\n", expectedHash: "",
    });
    assert.equal(created.saved, true);
  } finally { store.close(); }
});

test("tablet command waits for exact approval, executes once, and can be declined", async () => {
  const store = new Store(":memory:");
  const project = createCodeWorkspace(store, "Terminal test");
  const conversation = store.createConversation(project.id);
  store.update(conversation.id, { threadId: "thread-code", turnId: "turn-code" });
  let runs = 0;
  const replies: any[] = [];
  const rpc: any = { send: (message: any) => replies.push(message), stop: async () => {} };
  const host = new AgentHost(store, () => rpc, async (_workspace, command) => {
    runs++;
    return { command, exitCode: 0, stdout: "ok\n", stderr: "", truncated: false, timedOut: false };
  });
  const timer = setTimeout(() => {}, 30_000);
  host.active = { id: conversation.id, rpc, timer, finished: false, documentWrites: true,
    approvals: new Map(), pendingCommand: null, commandAbort: null };
  const request = (id: number, command: string) => host.handle(conversation.id, {
    id, method: "item/tool/call", params: { threadId: "thread-code", turnId: "turn-code",
      tool: "workspace_command", arguments: { command } },
  });
  try {
    request(1, "pwd");
    assert.equal(runs, 0);
    const proposal = store.events(conversation.id).find((e) => e.type === "command-proposal")!;
    assert.equal(proposal.data.command, "pwd");
    await host.resolveCommand(conversation.id, proposal.data.requestId, "approve");
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(runs, 1);
    assert.equal(replies.at(-1).result.success, true);
    await assert.rejects(host.resolveCommand(conversation.id, proposal.data.requestId, "approve"), /no longer pending/);
    request(2, "ls");
    const second = store.events(conversation.id).filter((e) => e.type === "command-proposal").at(-1)!;
    await host.resolveCommand(conversation.id, second.data.requestId, "decline");
    assert.equal(runs, 1);
    assert.match(replies.at(-1).result.contentItems[0].text, /declined/);
    request(3, "printf 'abc\u202e'");
    assert.equal(host.active?.pendingCommand, null);
    assert.throws(() => validateWorkspaceCommand("printf 'abc\u202e'"), /hidden/);
    host.active!.documentWrites = false;
    request(4, "pwd");
    assert.equal(host.active?.pendingCommand, null);
    assert.match(replies.at(-1).result.contentItems[0].text, /Full conversation/);
  } finally {
    await host.finish(conversation.id, "complete");
    store.close();
  }
});

test("engine recovery closes a command approval left pending by a crash", () => {
  const db = resolve(root, "recovery.sqlite");
  let store = new Store(db);
  const project = createCodeWorkspace(store, "Recover commands");
  const conversation = store.createConversation(project.id);
  store.update(conversation.id, { status: "waiting" });
  store.event(conversation.id, "command-proposal", { requestId: "proposal-1", command: "pwd", workspace: project.path });
  store.close();
  store = new Store(db);
  try {
    store.recover();
    assert.equal(store.conversation(conversation.id).status, "interrupted");
    assert.deepEqual(store.events(conversation.id).filter((e) => e.type === "command-resolved").map((e) => e.data), [
      { requestId: "proposal-1", decision: "interrupted" },
    ]);
  } finally { store.close(); }
});

test.after(() => rmSync(root, { recursive: true, force: true }));

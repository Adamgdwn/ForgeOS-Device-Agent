import test from "node:test";
import assert from "node:assert/strict";
import {
  emptyChat,
  recoverySnapshot,
  writeRecovery,
  invalidateRecovery,
  hydrateRecovery,
  flushRecovery,
} from "../src/recovery-store.ts";
const values = new Map<string, string>();
let failWrites = false;
Object.defineProperty(globalThis, "localStorage", {
  value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      if (failWrites) throw new Error("Full");
      values.set(key, value);
    },
    removeItem: (key: string) => {
      if (failWrites) throw new Error("Full");
      values.delete(key);
    },
  },
  configurable: true,
});
test("engine recovery restores without browser storage and serializes typing against the acknowledged version", async () => {
  const savedFetch = globalThis.fetch;
  Object.defineProperty(globalThis, "window", {
    value: {},
    configurable: true,
  });
  let revision = 7;
  let durable: any = { ...emptyChat, text: "Recovered from SQLite" };
  let release: (() => void) | undefined;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  let posts = 0;
  globalThis.fetch = async (_input, init) => {
    if (!init?.method)
      return Response.json({ found: true, value: durable, revision });
    const body = JSON.parse(String(init.body));
    assert.equal(body.revision, revision);
    if (++posts === 1) await blocked;
    durable = body.value;
    return Response.json({ revision: ++revision });
  };
  try {
    invalidateRecovery("durable");
    await hydrateRecovery("durable");
    assert.equal(recoverySnapshot("durable").value?.text, durable.text);
    writeRecovery("durable", { ...emptyChat, text: "First edit" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    writeRecovery("durable", { ...emptyChat, text: "Latest edit" });
    release!();
    await flushRecovery("durable");
    assert.equal(durable.text, "Latest edit");
    assert.equal(posts, 2);
    assert.equal(recoverySnapshot("durable").saving, false);
    values.clear();
    invalidateRecovery("durable");
    await hydrateRecovery("durable");
    assert.equal(recoverySnapshot("durable").value?.text, "Latest edit");
    writeRecovery("durable", null);
    await flushRecovery("durable");
    assert.equal(durable, null);
  } finally {
    globalThis.fetch = savedFetch;
    Reflect.deleteProperty(globalThis, "window");
    invalidateRecovery();
  }
});

test("draft recovery survives a fresh cache, isolates workspaces, and retains submission identity without resubmitting", () => {
  const pending = {
    id: "send-once",
    text: "Assess the material",
    composerText: "Assess the material",
    replyStyle: "standard",
    keepText: false,
    conversationId: "conversation-one",
  };
  const draft = {
    ...emptyChat,
    text: pending.text,
    attachments: ["Sources/agenda.pdf"],
    pending,
  };
  assert.equal(writeRecovery("instance:chat:one", draft), true);
  assert.equal(
    writeRecovery("instance:chat:two", {
      ...emptyChat,
      text: "Different discussion",
    }),
    true,
  );
  invalidateRecovery();
  assert.deepEqual(recoverySnapshot("instance:chat:one").value, draft);
  assert.equal(
    recoverySnapshot("instance:chat:two").value?.text,
    "Different discussion",
  );
  assert.equal(recoverySnapshot("another-instance:chat:one").value, null);
  writeRecovery("instance:chat:one", null);
  invalidateRecovery();
  assert.equal(recoverySnapshot("instance:chat:one").value, null);
});
test("report recovery retains its base hash and path; storage failure keeps current text and warns", () => {
  const draft = {
    kind: "report" as const,
    text: "Unsaved correction",
    hash: "earlier-version",
    path: "Reports/Summary.md",
  };
  writeRecovery("report", draft);
  invalidateRecovery();
  assert.deepEqual(recoverySnapshot("report").value, draft);
  failWrites = true;
  try {
    assert.equal(
      writeRecovery("report", { ...draft, text: "Most recent typing" }),
      false,
    );
    assert.equal(recoverySnapshot("report").value?.text, "Most recent typing");
    assert.match(recoverySnapshot("report").error, /recovery is unavailable/);
  } finally {
    failWrites = false;
  }
  values.set("galaxy-recovery-v1:invalid", "{broken");
  assert.match(recoverySnapshot("invalid").error, /Could not read/);
  assert.equal(values.get("galaxy-recovery-v1:invalid"), "{broken");
});

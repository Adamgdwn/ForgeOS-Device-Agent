import { createInterface } from "node:readline";
const send = (value) => process.stdout.write(JSON.stringify(value) + "\n");
createInterface({ input: process.stdin }).on("line", (line) => {
  const m = JSON.parse(line);
  if (m.id === "tablet-tool-1" && m.result) {
    send({
      method: "item/completed",
      params: {
        threadId: "tablet-thread",
        item: {
          type: "agentMessage",
          id: "answer",
          text: "Meeting sources checked.",
          phase: "final_answer",
        },
      },
    });
    send({
      method: "turn/completed",
      params: {
        threadId: "tablet-thread",
        turn: {
          id: "tablet-turn",
          status: m.result.success ? "completed" : "failed",
        },
      },
    });
    return;
  }
  if (m.method === "initialize")
    send({ id: m.id, result: { platformOs: "linux" } });
  if (["thread/start", "thread/resume"].includes(m.method))
    send({ id: m.id, result: { thread: { id: "tablet-thread" } } });
  if (m.method === "turn/start") {
    send({ id: m.id, result: { turn: { id: "tablet-turn" } } });
    send({
      method: "turn/started",
      params: { threadId: "tablet-thread", turn: { id: "tablet-turn" } },
    });
    send({
      id: "tablet-tool-1",
      method: "item/tool/call",
      params: {
        threadId: "tablet-thread",
        turnId: "tablet-turn",
        callId: "one",
        tool: "meeting_sources",
        arguments: {},
      },
    });
  }
});

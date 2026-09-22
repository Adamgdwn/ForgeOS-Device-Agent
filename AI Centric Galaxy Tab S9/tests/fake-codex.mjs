import { createInterface } from "node:readline";
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const send = (value) => process.stdout.write(JSON.stringify(value) + "\n");
let thread = "thread-fixture",
  turn = "turn-fixture";
createInterface({ input: process.stdin }).on("line", (line) => {
  const m = JSON.parse(line);
  if (!m.method) return;
  const result = (data) => send({ id: m.id, result: data });
  if (m.method === "initialize") result({ platformOs: "linux" });
  if (m.method === "thread/start" || m.method === "thread/resume") {
    thread = m.params.threadId || thread;
    result({ thread: { id: thread } });
  }
  if (m.method === "turn/start") {
    result({ turn: { id: turn } });
    send({
      method: "turn/started",
      params: { threadId: thread, turn: { id: turn } },
    });
    if (m.params.input[0].text.includes("hold")) {
      const child = spawn(
        process.execPath,
        ["-e", "setInterval(()=>{},1000)"],
        { stdio: "ignore" }
      );
      writeFileSync("child.pid", String(child.pid));
    } else
      setTimeout(() => {
        send({
          method: "item/agentMessage/delta",
          params: {
            threadId: thread,
            itemId: "message-1",
            delta: "Fixture answer",
          },
        });
        send({
          method: "item/completed",
          params: {
            threadId: thread,
            item: {
              id: "message-1",
              type: "agentMessage",
              text: "Fixture answer",
            },
          },
        });
        send({
          method: "turn/completed",
          params: { threadId: thread, turn: { id: turn, status: "completed" } },
        });
      }, 80);
  }
  if (m.method === "turn/steer") result({ turnId: turn });
  if (m.method === "turn/interrupt") {
    result({});
    send({
      method: "turn/completed",
      params: { threadId: thread, turn: { id: turn, status: "interrupted" } },
    });
  }
});

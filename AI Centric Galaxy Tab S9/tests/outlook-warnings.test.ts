import test from "node:test";
import assert from "node:assert/strict";
import { outlookWarnings } from "../src/outlook-warnings.ts";
import type { Activity } from "../src/api.ts";

test("Outlook sign-in warnings survive disappearing snackbars and clear on a new successful reading pass", () => {
  const events = [
    { type: "user", data: {} },
    { type: "notice", data: { warnings: ["Please sign in to Council."] } },
    { type: "notice", data: { warnings: ["Message collapsed"] } },
    { type: "notice", data: { warnings: [] } },
  ] as Activity[];
  assert.deepEqual(outlookWarnings(events), ["Please sign in to Council."]);
  events.push({ type: "user", data: {} } as Activity);
  assert.deepEqual(outlookWarnings(events), ["Please sign in to Council."]);
  events.push({
    type: "notice",
    data: { warnings: [] },
  } as unknown as Activity);
  assert.deepEqual(outlookWarnings(events), []);
});

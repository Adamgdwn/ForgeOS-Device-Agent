import test from "node:test";
import assert from "node:assert/strict";
import { answerForReport } from "../src/chat-content.ts";
import { meetingRequest, replyStyle } from "../server/meeting.ts";

test("moving an answer into a nested report retains source links, tables and literal examples", () => {
  const input =
    '[Email](Sources/Batch/Email%20notes.txt) and [reference][cost].\n\n[cost]: Sources/Cost.pdf "Estimate"\n\n[External](https://example.com/doc)\n\n| Item | Cost |\n| --- | --- |\n| Labour | 500 |\n\n`[literal](keep.txt)`\n\n```md\n[example](keep.txt)\n```';
  const result = answerForReport(input);
  assert.match(result, /\[Email\]\(\/Sources\/Batch\/Email%20notes.txt\)/);
  assert.match(result, /\[cost\]: \/Sources\/Cost.pdf "Estimate"/);
  assert.match(result, /https:\/\/example.com\/doc/);
  assert.match(result, /\| Labour\s*\| 500/);
  assert.match(result, /`\[literal\]\(keep.txt\)`/);
  assert.match(result, /\[example\]\(keep.txt\)/);
});

test("legacy messages keep their identity; meeting requests are distinct and unsupported styles fail", () => {
  assert.equal(replyStyle(undefined), "standard");
  assert.equal(meetingRequest("What changed?", "standard"), "What changed?");
  assert.notEqual(
    meetingRequest("What changed?", "quick"),
    meetingRequest("What changed?", "brief"),
  );
  assert.throws(() => replyStyle("write"), /Choose/);
  assert.throws(() => replyStyle(["quick"]), /Choose/);
});

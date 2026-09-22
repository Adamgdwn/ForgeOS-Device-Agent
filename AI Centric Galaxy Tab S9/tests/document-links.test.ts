import test from "node:test";
import assert from "node:assert/strict";
import { documentLink } from "../src/document-links.ts";

test("report citations resolve against their document folder and keep external URLs separate", () => {
  assert.equal(
    documentLink(
      "Reports/Summary report.md",
      "../Sources/meeting/Pasted%20email.txt",
    ),
    "Sources/meeting/Pasted email.txt",
  );
  assert.equal(
    documentLink("Summary report.md", "Sources/notes.txt"),
    "Sources/notes.txt",
  );
  assert.equal(
    documentLink("Reports/Summary report.md", "/Sources/notes.txt"),
    "Sources/notes.txt",
  );
  assert.equal(
    documentLink("Reports/report.md", "https://example.com/source"),
    null,
  );
  assert.equal(documentLink("Reports/report.md", "file:///etc/passwd"), null);
  assert.equal(documentLink("Reports/report.md", "%broken"), null);
});

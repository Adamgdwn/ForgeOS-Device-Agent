import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

const state = mkdtempSync(resolve(tmpdir(), "galaxy-cloud-documents-"));
process.env.GALAXY_STATE_DIR = state;
const { Store } = await import("../server/store.ts");
const { OneDrive } = await import("../server/onedrive.ts");
const { digest, readDocument } = await import("../server/files.ts");
const { stageUploads } = await import("../server/materials.ts");
const sample = readFileSync("tests/fixtures/sample.docx");
function fixture(
  location = "https://my.microsoftpersonalcontent.com/download?test=opaque",
  content = sample,
) {
  const store = new Store(":memory:");
  store.db
    .prepare(
      "UPDATE accounts SET homeId='personal-id', status='connected' WHERE slot=1",
    )
    .run();
  const item = {
    id: "file-1",
    name: "Meeting.docx",
    size: content.length,
    eTag: "version-1",
    webUrl: "https://onedrive.live.com/meeting",
    parentReference: { driveId: "drive-1" },
  };
  const calls: {
    url: string;
    headers: Headers;
    redirect?: RequestRedirect;
  }[] = [];
  const drive = new OneDrive(store, async (input, init) => {
    const url = String(input);
    calls.push({
      url,
      headers: new Headers(init?.headers),
      redirect: init?.redirect,
    });
    if (!url.startsWith("https://graph.microsoft.com/"))
      return new Response(content);
    if (url.endsWith("/content"))
      return new Response(null, {
        status: 302,
        headers: { Location: location },
      });
    return Response.json(item);
  });
  drive.token = async () => "test-graph-credential";
  return { store, drive, calls, item };
}
test("personal OneDrive preview and import download actual Word bytes without forwarding Graph authorization", async () => {
  const f = fixture();
  try {
    const expected = (
      await readDocument(resolve("tests/fixtures"), "sample.docx")
    ).text;
    const preview = await f.drive.preview(
      1,
      f.item.id,
      digest("personal-id"),
    );
    assert.equal(preview.text, expected);
    assert.ok(preview.text.length > 10);
    assert.equal(preview.source.originalName, "Meeting.docx");
    assert.equal(
      f.store.projects().length,
      0,
      "preview does not create a workspace",
    );
    assert.deepEqual(
      readdirSync(resolve(state, "staging")),
      [],
      "temporary preview bytes are removed",
    );
    const project = await f.drive.collect("Meeting", [
      { slot: 1, itemId: f.item.id },
    ]);
    const source = f.store.db
      .prepare("SELECT * FROM imports WHERE projectId=?")
      .get(project.id)!;
    assert.equal(source.etag, "version-1");
    assert.equal(source.homeId, "personal-id");
    assert.deepEqual(
      readFileSync(resolve(project.path, String(source.localName))),
      sample,
    );
    assert.equal(
      (await readDocument(project.path, String(source.localName))).text,
      expected,
    );
    const downloads = f.calls.filter(
      (c) => !c.url.startsWith("https://graph.microsoft.com/"),
    );
    assert.equal(downloads.length, 2);
    for (const call of downloads) {
      assert.equal(call.headers.get("Authorization"), null);
      assert.equal(call.redirect, "error");
    }
  } finally {
    f.store.close();
  }
});
test("file transfer rejects lookalike hosts, HTTP, credentials, local addresses and nonstandard ports before fetching", async () => {
  for (const url of [
    "https://my.microsoftpersonalcontent.com.evil.example/file",
    "https://evilmy.microsoftpersonalcontent.com/file",
    "http://my.microsoftpersonalcontent.com/file",
    "https://user:password@my.microsoftpersonalcontent.com/file",
    "https://my.microsoftpersonalcontent.com:444/file",
    "https://127.0.0.1/file",
    "https://evil.example/file",
  ]) {
    const f = fixture(url);
    try {
      await assert.rejects(
        f.drive.preview(1, f.item.id, digest("personal-id")),
        /unsupported file transfer host/,
      );
      assert.ok(
        f.calls.every((c) =>
          c.url.startsWith("https://graph.microsoft.com/"),
        ),
      );
      assert.equal(f.store.projects().length, 0);
    } finally {
      f.store.close();
    }
  }
});
test("preview rejects stale identities and files that change during download", async () => {
  const f = fixture();
  try {
    await assert.rejects(
      f.drive.preview(1, f.item.id, "old-identity"),
      /account changed/,
    );
    assert.equal(f.calls.length, 0);
    const fetcher = f.drive.fetcher;
    f.drive.fetcher = async (input, init) => {
      const response = await fetcher(input, init);
      if (!String(input).startsWith("https://graph.microsoft.com/"))
        f.item.eTag = "version-2";
      return response;
    };
    await assert.rejects(
      f.drive.preview(1, f.item.id, digest("personal-id")),
      /changed while opening/,
    );
    assert.equal(f.store.projects().length, 0);
  } finally {
    f.store.close();
  }
});
test("meeting PDF over 8 MB can be uploaded, read, previewed and imported while the 20 MB limit stays enforced", async () => {
  const original = readFileSync("tests/fixtures/sample.pdf");
  // Append a large PDF comment to exercise byte limits without a large fixture.
  const large = Buffer.concat([
    original,
    Buffer.from("\n%"),
    Buffer.alloc(14_000_000, 32),
    Buffer.from("\n%%EOF\n"),
  ]);
  const f = fixture(undefined, large);
  f.item.name = "Agenda.pdf";
  try {
    const stage = await stageUploads([
      { name: "Agenda.pdf", data: large.toString("base64") },
    ]);
    const uploaded = await readDocument(stage, "01-Agenda.pdf");
    assert.match(uploaded.text, /Workshop date: October 22/);
    const preview = await f.drive.preview(
      1,
      f.item.id,
      digest("personal-id"),
    );
    assert.equal(preview.text, uploaded.text);
    const project = await f.drive.collect("Agenda", [
      { slot: 1, itemId: f.item.id },
    ]);
    assert.ok(
      readdirSync(project.path).some((p) => p.endsWith("Agenda.pdf")),
    );
    f.item.size = 20_000_001;
    await assert.rejects(
      f.drive.preview(1, f.item.id, digest("personal-id")),
      /20 MB/,
    );
    await assert.rejects(
      f.drive.collect("Too large", [{ slot: 1, itemId: f.item.id }]),
      /20 MB/,
    );
  } finally {
    f.store.close();
  }
});
test.after(() => rmSync(state, { recursive: true, force: true }));

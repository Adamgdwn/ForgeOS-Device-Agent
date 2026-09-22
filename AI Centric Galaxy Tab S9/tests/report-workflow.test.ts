import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  readdirSync,
  rmSync,
  existsSync,
} from "node:fs";
import { resolve } from "node:path";
import { tmpdir } from "node:os";
import { randomUUID } from "node:crypto";
import { request } from "node:http";
import { execFileSync } from "node:child_process";
const root = mkdtempSync(resolve(tmpdir(), "galaxy-report-test-"));
process.env.GALAXY_STATE_DIR = resolve(root, "state");
process.env.GALAXY_ORIGIN = "http://localhost:4318";
const { Store } = await import("../server/store.ts");
const { application } = await import("../server/main.ts");
const { AgentHost } = await import("../server/codex.ts");
const { OneDrive } = await import("../server/onedrive.ts");
const { createCollection, stageUploads, installMaterials } =
  await import("../server/materials.ts");
const { prepareReport, saveReport, report, makeExport, exportFile } =
  await import("../server/reports.ts");
const { digest, changes } = await import("../server/files.ts");
const { PAIR_FILE } = await import("../server/auth.ts");
const file = (name: string, text: string) => ({
  name,
  data: Buffer.from(text).toString("base64"),
});

test("OneDrive material can be added to an existing report draft with pinned source identity and no extra workspace", async () => {
  const store = new Store(":memory:");
  const drive = new OneDrive(store, async (input) => {
    const url = String(input);
    if (url.endsWith("/content"))
      return new Response("Cloud decision: October 22");
    return Response.json({
      id: "cloud-notes",
      name: "notes.txt",
      size: 26,
      eTag: "version-one",
      webUrl: "https://example.sharepoint.com/notes.txt",
      parentReference: { driveId: "drive-one" },
    });
  });
  drive.token = async () => "FAKE_TOKEN";
  store.db
    .prepare(
      "UPDATE accounts SET homeId='identity-one', status='connected' WHERE slot=1",
    )
    .run();
  try {
    const project = createCollection(store, "Mixed sources"),
      conversation = store.createConversation(project.id);
    await prepareReport(store, conversation.id);
    saveReport(store, conversation.id, "# Keep this report", "");
    await assert.rejects(
      drive.collect("Same workspace", [
        { slot: 1, itemId: "cloud-notes", connectionId: "stale" },
      ]),
      /account changed/,
    );
    const added = await drive.collect(
      "Same workspace",
      [
        {
          slot: 1,
          itemId: "cloud-notes",
          connectionId: digest("identity-one"),
        },
      ],
      {
        projectId: project.id,
        conversationId: conversation.id,
        name: project.name,
      },
    );
    assert.equal(added.id, project.id);
    assert.equal(store.projects().length, 1);
    const source = store.db
      .prepare("SELECT * FROM imports WHERE projectId=?")
      .get(project.id) as any;
    assert.equal(source.homeId, "identity-one");
    assert.equal(source.etag, "version-one");
    assert.match(source.localName, /^Sources\//);
    assert.equal(
      readFileSync(
        resolve(
          store.conversation(conversation.id).workspace,
          source.localName,
        ),
        "utf8",
      ),
      "Cloud decision: October 22",
    );
    assert.deepEqual(
      (await changes(store.conversation(conversation.id), project)).map(
        (c) => c.path,
      ),
      ["Reports/Summary report.md"],
    );
  } finally {
    drive.close();
    store.close();
  }
});

test("email MIME is decoded, attachments included, remote HTML never fetched, invalid batch leaves no partial files", async () => {
  const email =
    "From: sender@example.com\r\nTo: reader@example.com\r\nSubject: =?UTF-8?B?UHJvamVjdCDigJMgTm90ZXM=?=\r\nDate: Mon, 21 Sep 2026 10:00:00 -0600\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=boundary123\r\n\r\n--boundary123\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Budget agreed: $1,200.</p><img src='https://example.com/tracker'><script>hiddenScript</script>\r\n--boundary123\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename=actions.txt\r\nContent-Transfer-Encoding: base64\r\n\r\nT3duZXI6IEFsZXg=\r\n--boundary123--\r\n";
  const stage = await stageUploads([file("message.eml", email)]);
  const extracted = readFileSync(
    resolve(stage, "01-message.eml.extracted.txt"),
    "utf8",
  );
  assert.match(extracted, /Project – Notes/);
  assert.match(extracted, /Budget agreed: \$1,200/);
  assert.doesNotMatch(extracted, /hiddenScript|tracker/);
  assert.equal(
    readFileSync(
      resolve(stage, "01-message.eml-attachment-1-actions.txt"),
      "utf8",
    ),
    "Owner: Alex",
  );
  rmSync(stage, { recursive: true });
  const before = readdirSync(resolve(root, "state/staging"));
  await assert.rejects(
    stageUploads([file("notes.txt", "good"), file("run.exe", "bad")]),
    /Use Word/,
  );
  await assert.rejects(
    stageUploads([{ name: "notes.txt", data: "AAAA===!" }]),
    /could not be read/,
  );
  assert.deepEqual(readdirSync(resolve(root, "state/staging")), before);
});

test("adding material after drafting retains report edits and source baselines; report editor rejects stale saves", async () => {
  const store = new Store(":memory:");
  try {
    const project = createCollection(store, "Source consolidation"),
      c = store.createConversation(project.id);
    await prepareReport(store, c.id);
    saveReport(store, c.id, "# My report\nExisting draft work", "");
    const stage = await stageUploads([file("notes.txt", "Meeting decision")], {
      subject: "Follow-up",
      from: "alex@example.com",
      text: "Delivery confirmed.",
    });
    await installMaterials(store, stage, {
      projectId: project.id,
      conversationId: c.id,
      name: project.name,
    });
    const updated = store.conversation(c.id),
      batch = readdirSync(resolve(project.path, "Sources"))[0];
    assert.equal(
      readFileSync(
        resolve(updated.workspace, "Sources", batch, "01-notes.txt"),
        "utf8",
      ),
      "Meeting decision",
    );
    assert.match(
      readFileSync(
        resolve(project.path, "Sources", batch, "Pasted email.txt"),
        "utf8",
      ),
      /Delivery confirmed/,
    );
    assert.equal(report(store, c.id).text, "# My report\nExisting draft work");
    assert.equal(
      existsSync(resolve(project.path, "Reports/Summary report.md")),
      false,
    );
    assert.deepEqual(
      (await changes(updated, project)).map((c) => c.path),
      ["Reports/Summary report.md"],
    );
    const snapshot = report(store, c.id);
    saveReport(store, c.id, "# Revised", snapshot.hash);
    assert.throws(
      () => saveReport(store, c.id, "Stale write", snapshot.hash),
      /changed while/,
    );
    assert.equal(report(store, c.id).text, "# Revised");
    await assert.rejects(prepareReport(store, c.id, "../outside.md"), /path/);
  } finally {
    store.close();
  }
});

test("Word and PDF exports contain the report, omit embedded resource reads, and preserve the working draft", async () => {
  const store = new Store(":memory:");
  try {
    const p = createCollection(store, "Export"),
      c = store.createConversation(p.id);
    await prepareReport(store, c.id);
    const secret = resolve(root, "must-not-embed.txt");
    writeFileSync(secret, "PRIVATE_RESOURCE_SENTINEL");
    const snapshot = saveReport(
      store,
      c.id,
      `# Summary report\n\nDecision confirmed. Owner: Alex.\n\n![never load](${secret})\n\n[Source](Sources/notes.txt)\n`,
      "",
    );
    await assert.rejects(makeExport(store, c.id, "md", "oldhash"), /changed/);
    for (const format of ["docx", "pdf", "md"]) {
      const out = await makeExport(store, c.id, format, snapshot.hash);
      const data = readFileSync(exportFile(out));
      assert.ok(data.length > 0);
      let text = data.toString("utf8");
      if (format === "docx")
        text = execFileSync("pandoc", [exportFile(out), "-t", "plain"], {
          encoding: "utf8",
          timeout: 15000,
        });
      if (format === "pdf") {
        assert.equal(data.subarray(0, 4).toString(), "%PDF");
        text = execFileSync("pdftotext", [exportFile(out), "-"], {
          encoding: "utf8",
          timeout: 15000,
        });
      }
      assert.match(text, /Decision confirmed/);
      assert.doesNotMatch(text, /PRIVATE_RESOURCE_SENTINEL/);
    }
    assert.equal(report(store, c.id).hash, snapshot.hash);
  } finally {
    store.close();
  }
});

test("OneDrive new-file export pins the account and folder, refuses replacement and never sends a bearer to the upload host", async () => {
  const store = new Store(":memory:");
  const calls: { url: string; init: RequestInit }[] = [];
  const drive = new OneDrive(store, async (input, init = {}) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("createUploadSession")) {
      assert.equal(
        JSON.parse(String(init.body)).item["@microsoft.graph.conflictBehavior"],
        "fail",
      );
      return Response.json({
        uploadUrl: "https://files.sharepoint.com/upload",
      });
    }
    if (url.includes("/upload")) {
      assert.equal((init.headers as any).Authorization, undefined);
      return Response.json(
        {
          id: "new",
          name: "Report.docx",
          webUrl: "https://files.sharepoint.com/Report.docx",
        },
        { status: 201 },
      );
    }
    return Response.json({ id: "folder-123", folder: { childCount: 0 } });
  });
  store.db
    .prepare(
      "UPDATE accounts SET homeId='identity-one', username='test@example.com', status='connected' WHERE slot=1",
    )
    .run();
  drive.token = async () => "FAKE_BEARER";
  try {
    await assert.rejects(
      drive.publishNew(
        1,
        "folder-123",
        "Report.docx",
        Buffer.from("x"),
        "wrong",
      ),
      /currently connected/,
    );
    assert.equal(calls.length, 0);
    const result = await drive.publishNew(
      1,
      "folder-123",
      "Report.docx",
      Buffer.from("x"),
      digest("identity-one"),
    );
    assert.match(result.webUrl, /Report.docx/);
    assert.ok(
      calls.some((c) =>
        c.url.includes("items/folder-123:/Report.docx:/createUploadSession"),
      ),
    );
    const count = calls.length;
    await assert.rejects(
      drive.publishNew(
        1,
        "root",
        "../bad.docx",
        Buffer.from("x"),
        digest("identity-one"),
      ),
      /valid new filename/,
    );
    assert.equal(calls.length, count);
  } finally {
    drive.close();
    store.close();
  }
});

test("HTTP gather → draft → export is authenticated, repeat imports are idempotent, active work blocks additions, uncertain cloud upload is never replayed", async () => {
  const store = new Store(":memory:"),
    host = new AgentHost(store),
    drive = new OneDrive(store);
  host.status = async () => ({
    available: true,
    compatible: true,
    version: "fixture",
    expected: "fixture",
    activeConversation: host.active?.id || null,
  });
  let publications = 0;
  drive.publishNew = async () => {
    publications++;
    throw new Error("Connection dropped after submission");
  };
  const app = application(store, host, drive);
  await new Promise<void>((r) => app.server.listen(0, "127.0.0.1", r));
  const port = (app.server.address() as any).port;
  let cookie = "";
  async function call(path: string, method = "GET", data?: any, paired = true) {
    return await new Promise<{ status: number; data: any; bytes: Buffer }>(
      (done, reject) => {
        const req = request(
          {
            host: "127.0.0.1",
            port,
            path,
            method,
            headers: {
              Host: "localhost:4318",
              Origin: "http://localhost:4318",
              "X-Galaxy-Request": "1",
              "Content-Type": "application/json",
              ...(paired ? { Cookie: cookie } : {}),
            },
          },
          (res) => {
            if (res.headers["set-cookie"])
              cookie = res.headers["set-cookie"][0].split(";")[0];
            const chunks: Buffer[] = [];
            res.on("data", (b) => chunks.push(b));
            res.on("end", () => {
              const bytes = Buffer.concat(chunks);
              let data;
              try {
                data = JSON.parse(bytes.toString());
              } catch {
                data = bytes.toString();
              }
              done({ status: res.statusCode!, data, bytes });
            });
          },
        );
        req.on("error", reject);
        req.end(data === undefined ? undefined : JSON.stringify(data));
      },
    );
  }
  try {
    assert.equal((await call("/api/materials", "POST", {}, false)).status, 401);
    await call("/api/session", "POST", {
      code: readFileSync(PAIR_FILE, "utf8"),
    });
    const p = (
      await call("/api/workspaces", "POST", { name: "Workflow fixture" })
    ).data;
    const c = (await call("/api/conversations", "POST", { projectId: p.id }))
      .data;
    const payload = {
      id: randomUUID(),
      projectId: p.id,
      conversationId: c.id,
      files: [file("minutes.txt", "Decision: approve timeline")],
    };
    const imported = await call("/api/materials", "POST", payload);
    assert.equal(imported.status, 200, JSON.stringify(imported.data));
    assert.equal((await call("/api/materials", "POST", payload)).status, 200);
    assert.equal(readdirSync(resolve(p.path, "Sources")).length, 1);
    assert.equal(
      (
        await call("/api/materials", "POST", {
          ...payload,
          files: [file("changed.txt", "different")],
        })
      ).status,
      400,
    );
    host.active = { id: c.id } as any;
    assert.match(
      (await call("/api/materials", "POST", { ...payload, id: randomUUID() }))
        .data.error,
      /finish/,
    );
    host.active = null;
    assert.equal(
      (await call(`/api/conversations/${c.id}/report`, "POST", {})).status,
      200,
    );
    const saved = await call(`/api/conversations/${c.id}/report`, "POST", {
      text: "# Summary\nApproved timeline.",
      hash: "",
    });
    assert.equal(saved.status, 200);
    const exported = await call(`/api/conversations/${c.id}/export`, "POST", {
      format: "md",
      hash: saved.data.hash,
    });
    assert.equal(exported.status, 200);
    const url = `/api/exports/${exported.data.id}`;
    assert.equal(
      (await call(url + "/download", "GET", undefined, false)).status,
      401,
    );
    assert.match((await call(url + "/download")).data, /Approved timeline/);
    const destination = {
      slot: 1,
      parentId: "root",
      name: "Summary.md",
      connectionId: "fixture",
    };
    assert.equal(
      (await call(url + "/onedrive", "POST", destination)).status,
      400,
    );
    assert.match(
      (await call(url + "/onedrive", "POST", destination)).data.error,
      /already submitted/,
    );
    assert.equal(publications, 1);
  } finally {
    host.active = null;
    await app.close();
  }
});
test.after(() => rmSync(root, { recursive: true, force: true }));

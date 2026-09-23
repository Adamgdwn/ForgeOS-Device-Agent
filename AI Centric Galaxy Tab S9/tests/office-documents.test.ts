import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  rmSync,
  readFileSync,
  writeFileSync,
  readdirSync,
  symlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";
const state = mkdtempSync(resolve(tmpdir(), "galaxy-office-"));
process.env.GALAXY_STATE_DIR = resolve(state, "state");
const { readDocument, digest } = await import("../server/files.ts");
const { Store } = await import("../server/store.ts");
const { stageUploads, installMaterials } =
  await import("../server/materials.ts");
const { documentEntries, documentDownload } =
  await import("../server/documents.ts");

test("Excel and PowerPoint imports preserve original bytes, expose bounded referenced text, and group sidecars", async () => {
  const store = new Store(":memory:");
  try {
    const originals = ["workflow-budget.xlsx", "workflow-slides.pptx"].map(
      (name) => ({
        name,
        bytes: readFileSync(resolve("tests/fixtures", name)),
      }),
    );
    const stage = await stageUploads(
      originals.map((f) => ({
        name: f.name,
        data: f.bytes.toString("base64"),
      })),
    );
    const p = await installMaterials(store, stage, { name: "Office workflow" });
    const displayed = documentEntries(store, p, p.path, "");
    assert.equal(displayed.length, 3);
    assert.equal(readdirSync(p.path).length, 5);
    for (const source of originals) {
      const entry = displayed.find((f) => f.displayName === source.name)!;
      assert.ok(entry.extractionPath);
      assert.equal(entry.role, "Imported snapshot");
      const download = documentDownload(store, p, p.path, entry.path);
      assert.equal(digest(download.bytes), digest(source.bytes));
      const text = await readDocument(p.path, entry.path);
      assert.equal(text.extracted, true);
      assert.equal(text.truncated, false);
      if (source.name.endsWith("xlsx")) {
        assert.match(text.text, /Sheet: Operations budget/);
        assert.match(text.text, /B2: 12000/);
        assert.match(text.text, /D2:.*formula: B2-C2; cached result/);
        assert.match(text.text, /Sheet: Council notes/);
        assert.match(text.text, /not recalculated/);
      } else {
        assert.match(text.text, /Slide 1[\s\S]*Council preparation/);
        assert.match(text.text, /Slide 2[\s\S]*Owner: Alex/);
        assert.match(text.text, /charts.*not assessed/);
      }
    }
    assert.throws(
      () => documentDownload(store, p, p.path, "../secret.txt"),
      /path/,
    );
    writeFileSync(resolve(p.path, "unsafe.html"), "<script>bad()</script>");
    assert.throws(
      () => documentDownload(store, p, p.path, "unsafe.html"),
      /type or size/,
    );
    symlinkSync(originals[0].name, resolve(p.path, "linked.xlsx"));
    assert.throws(() => documentDownload(store, p, p.path, "linked.xlsx"));
  } finally {
    store.close();
  }
});

test("Office extraction labels truncation and rejects XML declarations, malformed archives, and missing external sheets", async () => {
  const python = String.raw`
import sys, zipfile
from pathlib import Path
root=Path(sys.argv[1])
source=Path('tests/fixtures/workflow-budget.xlsx')
for mode in ['long', 'declaration', 'external']:
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(root/(mode+'.xlsx'), 'w') as dst:
        for info in src.infolist():
            data=src.read(info.filename)
            if info.filename=='xl/worksheets/sheet1.xml':
                if mode=='long': data=data.replace(b'Maintenance', b'x'*120000)
                if mode=='declaration': data=b'<!DOCTYPE worksheet [<!ENTITY test "bad">]>'+data
            if mode=='external' and info.filename=='xl/_rels/workbook.xml.rels':
                data=data.replace(b'Target="/xl/worksheets/sheet1.xml"', b'Target="https://example.invalid/private" TargetMode="External"')
            dst.writestr(info.filename, data)
`;
  execFileSync("python3", ["-c", python, state], { timeout: 10000 });
  const long = await readDocument(state, "long.xlsx");
  assert.equal(long.truncated, true);
  assert.equal(long.text.length, 100000);
  for (const name of ["declaration.xlsx", "external.xlsx"])
    await assert.rejects(
      readDocument(state, name),
      /Office text could not be read/,
    );
  writeFileSync(resolve(state, "broken.pptx"), "Not an Office archive");
  await assert.rejects(
    readDocument(state, "broken.pptx"),
    /Office text could not be read/,
  );
});
test.after(() => rmSync(state, { recursive: true, force: true }));

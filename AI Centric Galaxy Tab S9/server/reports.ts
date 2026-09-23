import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  lstatSync,
} from "node:fs";
import { resolve, join, basename, extname } from "node:path";
import { pathToFileURL } from "node:url";
import { randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { STATE, privateWrite } from "./config.ts";
import { createDraft, digest, safePath } from "./files.ts";
import type { Store } from "./store.ts";

const execute = promisify(execFile);
export const formats = {
  md: "text/markdown; charset=utf-8",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pdf: "application/pdf",
};
export type ExportFormat = keyof typeof formats;
export type ExportRecord = {
  id: string;
  conversationId: string;
  filename: string;
  format: ExportFormat;
  hash: string;
  cloudState: string;
  webUrl: string;
  createdAt: string;
  destination: string;
};
export function reportPath(store: Store, id: string) {
  return (
    (
      store.db
        .prepare("SELECT path FROM reports WHERE conversationId=?")
        .get(id) as { path: string } | undefined
    )?.path || "Reports/Summary report.md"
  );
}
export function report(store: Store, id: string) {
  const c = store.conversation(id),
    path = reportPath(store, id),
    full = safePath(c.workspace, path);
  const configured = !!store.db
    .prepare("SELECT 1 FROM reports WHERE conversationId=?")
    .get(id);
  if (!existsSync(full))
    return { path, configured, exists: false, text: "", hash: "" };
  if (!lstatSync(full).isFile() || lstatSync(full).size > 500_000)
    throw new Error("The report must be a text document under 500 KB.");
  const bytes = readFileSync(full);
  if (bytes.includes(0)) throw new Error("Choose a Markdown or text report.");
  return {
    path,
    configured,
    exists: true,
    text: bytes.toString("utf8"),
    hash: digest(bytes),
  };
}
export async function prepareReport(store: Store, id: string, path?: string) {
  let c = store.conversation(id);
  const selected = path || reportPath(store, id);
  if (!/\.(md|txt)$/i.test(selected) || selected.length > 300)
    throw new Error("Choose a Markdown or text report filename.");
  safePath(c.workspace, selected);
  if (c.mode !== "draft")
    c = store.update(id, {
      workspace: await createDraft(store.project(c.projectId), id),
      mode: "draft",
    });
  store.db
    .prepare(
      "INSERT INTO reports VALUES (?, ?) ON CONFLICT(conversationId) DO UPDATE SET path=excluded.path",
    )
    .run(id, selected);
  store.event(id, "notice", {
    text: `Report ready to draft at ${selected}. Continue the conversation to create or refine it.`,
  });
  return report(store, id);
}
export function saveReport(
  store: Store,
  id: string,
  text: unknown,
  hash: unknown,
  expectedPath?: unknown,
) {
  const c = store.conversation(id),
    current = report(store, id);
  if (c.mode !== "draft" || !current.configured)
    throw new Error("Start a report draft first.");
  if (
    typeof text !== "string" ||
    !text.trim() ||
    Buffer.byteLength(text) > 500_000 ||
    text.includes("\0")
  )
    throw new Error("A report needs text and must be under 500 KB.");
  if (
    hash !== current.hash ||
    (expectedPath !== undefined && expectedPath !== current.path)
  )
    throw new Error(
      "The report changed while you were editing. Your text is kept here; reload the latest version before saving.",
    );
  const target = safePath(c.workspace, current.path);
  mkdirSync(resolve(target, ".."), { recursive: true, mode: 0o700 });
  privateWrite(target, text);
  store.event(id, "notice", { text: `Report updated: ${current.path}` });
  return report(store, id);
}
// Only textual document content reaches converters. No images, raw markup, or local-resource links.
function cleanAst(node: any): any {
  if (Array.isArray(node)) return node.map(cleanAst);
  if (!node || typeof node !== "object") return node;
  if (["Image", "RawBlock", "RawInline"].includes(node.t))
    return {
      t: node.t === "RawBlock" ? "Para" : "Str",
      c:
        node.t === "RawBlock"
          ? [{ t: "Str", c: "[Embedded content omitted]" }]
          : "[Embedded content omitted]",
    };
  if (node.t === "Link" && !/^https?:\/\//i.test(node.c?.[2]?.[0] || ""))
    return {
      t: "Span",
      c: [
        ["", [], []],
        [
          ...cleanAst(node.c[1]),
          { t: "Str", c: ` (${String(node.c[2][0]).slice(0, 500)})` },
        ],
      ],
    };
  return Object.fromEntries(
    Object.entries(node).map(([key, value]) => [key, cleanAst(value)]),
  );
}
export function exportRecord(store: Store, id: string) {
  const row = store.db.prepare("SELECT * FROM exports WHERE id=?").get(id) as
    ExportRecord | undefined;
  if (!row)
    throw new Error("Export not found. Create a fresh export from the report.");
  return row;
}
export function exportFile(row: ExportRecord) {
  return resolve(STATE, "exports", `${row.id}.${row.format}`);
}
export async function makeExport(
  store: Store,
  id: string,
  format: string,
  expectedHash: string,
) {
  if (!Object.hasOwn(formats, format))
    throw new Error("Choose Word, PDF, or Markdown.");
  const current = report(store, id);
  if (!current.exists || !current.text.trim())
    throw new Error("Draft your report before exporting it.");
  if (current.hash !== expectedHash)
    throw new Error("The report changed. Refresh it before exporting.");
  const parent = resolve(STATE, "exports");
  mkdirSync(parent, { recursive: true, mode: 0o700 });
  const temp = mkdtempSync(join(parent, ".convert-"));
  const exportId = randomUUID(),
    output = resolve(parent, `${exportId}.${format}`);
  try {
    if (format === "md") privateWrite(output, current.text);
    else {
      const source = resolve(temp, "report.md"),
        ast = resolve(temp, "report.json"),
        docx = resolve(temp, "report.docx");
      privateWrite(source, current.text);
      const options = {
        timeout: 20_000,
        maxBuffer: 5_000_000,
        cwd: temp,
        env: {
          PATH: process.env.PATH,
          HOME: temp,
          LANG: "C.UTF-8",
          OMP_NUM_THREADS: "1",
          TMPDIR: temp,
        },
      };
      const parsed = JSON.parse(
        (
          await execute(
            "pandoc",
            ["--sandbox", "--from=gfm", "--to=json", source],
            options,
          )
        ).stdout,
      );
      parsed.meta = {};
      privateWrite(ast, JSON.stringify(cleanAst(parsed)));
      await execute(
        "pandoc",
        [
          "--sandbox",
          `--data-dir=${temp}`,
          "--from=json",
          "--to=docx",
          "--output",
          docx,
          ast,
        ],
        options,
      );
      if (format === "pdf" && process.env.GALAXY_PDF_ENGINE === "typst") {
        // Android has native Pandoc/Typst packages. Only the sanitized AST
        // reaches this engine; source markup and local resources are removed.
        await execute(
          "pandoc",
          [
            "--sandbox",
            `--data-dir=${temp}`,
            "--from=json",
            "--to=typst",
            "--pdf-engine=typst",
            "--output",
            resolve(temp, "report.pdf"),
            ast,
          ],
          {
            ...options,
            timeout: 40_000,
            env: { ...options.env, TYPST_FONT_PATHS: "/system/fonts" },
          },
        );
      } else if (format === "pdf")
        await execute(
          "timeout",
          [
            "--signal=TERM",
            "--kill-after=3s",
            "35s",
            "libreoffice",
            `-env:UserInstallation=${pathToFileURL(resolve(temp, "profile")).href}`,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            temp,
            docx,
          ],
          { ...options, timeout: 40_000 },
        );
      const data = readFileSync(resolve(temp, `report.${format}`));
      if (!data.length || data.length > 8_000_000)
        throw new Error("Export is too large.");
      privateWrite(output, data);
    }
    const filename =
      basename(current.path, extname(current.path)) + `.${format}`;
    store.db
      .prepare(
        "INSERT INTO exports(id,conversationId,filename,format,hash,createdAt) VALUES (?,?,?,?,?,?)",
      )
      .run(
        exportId,
        id,
        filename,
        format,
        current.hash,
        new Date().toISOString(),
      );
    return exportRecord(store, exportId);
  } catch {
    rmSync(output, { force: true });
    throw new Error(
      "Report export could not finish. Your draft is saved. Try Markdown, or check that Pandoc and LibreOffice are available on the workstation.",
    );
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
}

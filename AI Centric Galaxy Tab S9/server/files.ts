import {
  existsSync,
  realpathSync,
  lstatSync,
  readdirSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  copyFileSync,
  renameSync,
  unlinkSync,
} from "node:fs";
import {
  resolve,
  relative,
  join,
  dirname,
  extname,
  isAbsolute,
  sep,
} from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createHash, randomUUID } from "node:crypto";
import { createPatch } from "diff";
import mammoth from "mammoth";
import { STATE, ROOT, privateWrite } from "./config.ts";
import type { Project, Conversation } from "./store.ts";
import {
  documentByteLimit,
  DOCUMENT_LIMIT_MESSAGE,
} from "../shared/document-limits.ts";

const execute = promisify(execFile);
const excluded = new Set([
  "node_modules",
  "dist",
  "build",
  "target",
  "__pycache__",
  "vendor",
]);
export function visible(name: string) {
  return (
    !name.startsWith(".") &&
    !excluded.has(name) &&
    !/^(?:credentials|secrets?|auth|pairing-code)(?:\.|$)/i.test(name) &&
    !/\.(?:pem|key|p12|pfx)$/i.test(name)
  );
}
export function safePath(root: string, input = ""): string {
  if (
    isAbsolute(input) ||
    input.includes("\0") ||
    input.includes("\\") ||
    input.split("/").some((p) => p === ".." || (p && !visible(p)))
  )
    throw new Error("This path is not available in the workspace.");
  const base = realpathSync(root),
    target = resolve(base, input),
    rel = relative(base, target);
  if (rel.startsWith("..") || isAbsolute(rel))
    throw new Error("Path is outside this workspace.");
  let current = base;
  for (const part of rel.split(sep).filter(Boolean)) {
    current = join(current, part);
    if (existsSync(current) && lstatSync(current).isSymbolicLink())
      throw new Error("Symbolic links are not included in this pilot.");
  }
  return target;
}
export function listFiles(root: string, path = "") {
  const entries = readdirSync(safePath(root, path), {
    withFileTypes: true,
  }).filter((f) => visible(f.name) && !f.isSymbolicLink());
  if (entries.length > 2000)
    throw new Error(
      "This folder has too many entries for the pilot. Register a smaller folder.",
    );
  return entries
    .map((f) => {
      const p = path ? `${path}/${f.name}` : f.name,
        stat = lstatSync(safePath(root, p));
      return {
        name: f.name,
        path: p,
        directory: f.isDirectory(),
        size: stat.size,
        modified: stat.mtime.toISOString(),
      };
    })
    .sort(
      (a, b) =>
        Number(b.directory) - Number(a.directory) ||
        a.name.localeCompare(b.name),
    );
}
export async function readDocument(root: string, path: string) {
  const full = safePath(root, path),
    stat = lstatSync(full),
    ext = extname(path).toLowerCase();
  if (!stat.isFile() || stat.size > documentByteLimit(path))
    throw new Error(DOCUMENT_LIMIT_MESSAGE);
  let text: string;
  let officeTruncated = false;
  if ([".xlsx", ".pptx"].includes(ext)) {
    try {
      const result = JSON.parse(
        (
          await execute(
            "python3",
            [resolve(ROOT, "server/office-text.py"), full],
            { timeout: 15_000, maxBuffer: 1_000_000 },
          )
        ).stdout,
      );
      text = result.text;
      officeTruncated = result.truncated;
    } catch {
      throw new Error(
        "Office text could not be read. Open the original in Excel or PowerPoint; encrypted, malformed or oversized content is unsupported.",
      );
    }
  } else if (ext === ".eml") {
    const extracted = safePath(root, path + ".extracted.txt");
    text =
      existsSync(extracted) && lstatSync(extracted).size <= 500_000
        ? readFileSync(extracted, "utf8")
        : JSON.parse(
            (
              await execute(
                "python3",
                [resolve(ROOT, "server/email-text.py"), full],
                { timeout: 15_000, maxBuffer: 16_000_000 },
              )
            ).stdout,
          ).text;
  } else if (ext === ".docx")
    text = (await mammoth.extractRawText({ path: full })).value;
  else if (ext === ".pdf") {
    try {
      text = (
        await execute("pdftotext", ["-layout", full, "-"], {
          timeout: 15_000,
          maxBuffer: 2_000_000,
        })
      ).stdout;
    } catch {
      throw new Error(
        "PDF text extraction was unavailable. Scanned PDFs need OCR, which is not included yet.",
      );
    }
  } else {
    if (stat.size > 500_000)
      throw new Error("Text preview supports files up to 500 KB.");
    const data = readFileSync(full);
    if (data.includes(0))
      throw new Error("This file format cannot be previewed as text yet.");
    text = data.toString("utf8");
  }
  return {
    path,
    text: text.slice(0, 100_000),
    truncated: officeTruncated || text.length > 100_000,
    extracted: [".docx", ".xlsx", ".pptx", ".pdf", ".eml"].includes(ext),
  };
}
export const digest = (data: string | Buffer) =>
  createHash("sha256").update(data).digest("hex");
export async function git(cwd: string, args: string[]) {
  return (
    await execute(
      "git",
      ["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", ...args],
      { cwd, timeout: 20_000, maxBuffer: 3_000_000 },
    )
  ).stdout;
}
function inventory(root: string) {
  const paths: string[] = [];
  let bytes = 0;
  function walk(path = "") {
    for (const file of listFiles(root, path)) {
      if (file.directory) walk(file.path);
      else {
        bytes += file.size;
        paths.push(file.path);
        if (paths.length > 2000 || bytes > 60_000_000)
          throw new Error(
            "This folder is too large for a pilot draft. Register a smaller project folder (up to 2,000 files / 60 MB).",
          );
      }
    }
  }
  walk();
  return paths;
}
export async function createDraft(
  project: Project,
  conversationId: string,
): Promise<string> {
  if (project.kind === "system")
    throw new Error(
      "System uses reviewed tablet settings, not a document draft.",
    );
  const paths = inventory(project.path),
    root = resolve(STATE, "drafts", `${conversationId}-${randomUUID()}`);
  mkdirSync(root, { recursive: true, mode: 0o700 });
  const baseline: Record<string, string> = {};
  for (const path of paths) {
    const source = safePath(project.path, path),
      dest = safePath(root, path);
    const contents = readFileSync(source);
    baseline[path] = digest(contents);
    mkdirSync(dirname(dest), { recursive: true });
    writeFileSync(dest, contents);
  }
  await git(root, ["init", "-q"]);
  await git(root, ["add", "--all"]);
  await git(root, [
    "-c",
    "user.name=Galaxy Workspace",
    "-c",
    "user.email=galaxy@localhost",
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "Snapshot of selected working files",
  ]);
  privateWrite(`${root}.baseline.json`, JSON.stringify(baseline));
  return root;
}
export type Change = {
  path: string;
  kind: string;
  diff: string;
  applicable: boolean;
  conflict: boolean;
};
export async function changes(
  c: Conversation,
  project: Project,
): Promise<Change[]> {
  if (c.mode !== "draft") return [];
  const baseline = JSON.parse(
    readFileSync(`${c.workspace}.baseline.json`, "utf8"),
  ) as Record<string, string>;
  const paths = [
    ...new Set([...Object.keys(baseline), ...inventory(c.workspace)]),
  ];
  const result: Change[] = [];
  for (const path of paths) {
    const draft = safePath(c.workspace, path),
      exists = existsSync(draft);
    const after = exists ? readFileSync(draft) : Buffer.alloc(0);
    if (exists && digest(after) === baseline[path]) continue;
    if (!exists && !(path in baseline)) continue;
    const before =
      path in baseline ? await git(c.workspace, ["show", `HEAD:${path}`]) : "";
    const source = safePath(project.path, path);
    const sourceHash = existsSync(source)
      ? digest(readFileSync(source))
      : undefined;
    const text =
      !after.includes(0) &&
      after.length < 500_000 &&
      ![".docx", ".pdf"].includes(extname(path).toLowerCase());
    result.push({
      path,
      kind: !exists ? "deleted" : !(path in baseline) ? "added" : "modified",
      diff: text
        ? createPatch(path, before, after.toString("utf8"))
        : "Binary or large-file review is not supported yet.",
      applicable: text && exists,
      conflict: sourceHash !== baseline[path],
    });
  }
  return result;
}
export async function applyLocalChange(
  c: Conversation,
  project: Project,
  path: string,
) {
  const change = (await changes(c, project)).find((ch) => ch.path === path);
  if (!change?.applicable)
    throw new Error(
      "This change cannot be applied from the pilot. Deletions and binary changes require manual review.",
    );
  if (change.conflict)
    throw new Error(
      "The source changed since this draft started. Your draft is preserved; reconcile it before applying.",
    );
  const target = safePath(project.path, path),
    draft = safePath(c.workspace, path);
  mkdirSync(dirname(target), { recursive: true });
  const temp = join(dirname(target), `.galaxy-${randomUUID()}`);
  try {
    copyFileSync(draft, temp);
    renameSync(temp, target);
  } finally {
    if (existsSync(temp)) unlinkSync(temp);
  }
  await checkpointDraft(c.workspace, path);
}
export async function checkpointDraft(workspace: string, path: string) {
  const manifest = JSON.parse(
    readFileSync(`${workspace}.baseline.json`, "utf8"),
  );
  manifest[path] = digest(readFileSync(safePath(workspace, path)));
  await git(workspace, ["add", "--", path]);
  await git(workspace, [
    "-c",
    "user.name=Galaxy Workspace",
    "-c",
    "user.email=galaxy@localhost",
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "Checkpoint of reviewed save",
    "--",
    path,
  ]);
  privateWrite(`${workspace}.baseline.json`, JSON.stringify(manifest));
}

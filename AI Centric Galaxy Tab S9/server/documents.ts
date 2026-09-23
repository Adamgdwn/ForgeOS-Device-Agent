import { existsSync, lstatSync, readFileSync } from "node:fs";
import { basename } from "node:path";
import { listFiles, safePath } from "./files.ts";
import type { Store, Project } from "./store.ts";
import { documentType } from "../shared/document-types.ts";
import { documentByteLimit } from "../shared/document-limits.ts";

export function documentDownload(
  store: Store,
  project: Project,
  root: string,
  path: string,
) {
  if (project.kind === "system")
    throw new Error("Use My Files to open shared tablet documents.");
  const full = safePath(root, path),
    type = documentType(path),
    stat = lstatSync(full);
  if (!type || !stat.isFile() || stat.size > documentByteLimit(path))
    throw new Error("This document type or size cannot be downloaded here.");
  const source = store.db
    .prepare(
      "SELECT originalName FROM imports WHERE projectId=? AND localName=?",
    )
    .get(project.id, path);
  return {
    bytes: readFileSync(full),
    type,
    filename: String(source?.originalName || basename(path)),
  };
}

/** Presentation only: original paths and model tool access remain unchanged. */
export function documentEntries(
  store: Store,
  project: Project,
  root: string,
  path: string,
) {
  const entries = listFiles(root, path);
  const paths = new Set(entries.filter((e) => !e.directory).map((e) => e.path));
  const imported = existsSync(
    safePath(root, path ? `${path}/SOURCE_INDEX.md` : "SOURCE_INDEX.md"),
  );
  const sources = new Map(
    store.db
      .prepare("SELECT localName, originalName FROM imports WHERE projectId=?")
      .all(project.id)
      .map((s) => [String(s.localName), String(s.originalName)]),
  );
  return entries
    .filter(
      (e) =>
        !e.path.endsWith(".extracted.txt") || !paths.has(e.path.slice(0, -14)),
    )
    .map((entry) => ({
      ...entry,
      displayName:
        sources.get(entry.path) ||
        (imported && !entry.directory
          ? entry.name.replace(/^\d{2}-/, "")
          : entry.name),
      role: entry.directory
        ? "Folder"
        : entry.name === "SOURCE_INDEX.md"
          ? "Source details"
          : sources.has(entry.path) || imported
            ? "Imported snapshot"
            : root !== project.path
              ? "Working copy"
              : "Workspace file",
      extractionPath: paths.has(entry.path + ".extracted.txt")
        ? entry.path + ".extracted.txt"
        : undefined,
    }));
}

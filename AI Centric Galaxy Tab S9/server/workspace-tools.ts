import { existsSync, readFileSync, mkdirSync, renameSync, lstatSync, unlinkSync, chmodSync } from "node:fs";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";
import { createPatch } from "diff";
import { privateWrite } from "./config.ts";
import { listFiles, readDocument, safePath, digest } from "./files.ts";
import { prepareReport, report, saveReport } from "./reports.ts";
import type { Store } from "./store.ts";
const tool = (
  name: string,
  description: string,
  properties: Record<string, unknown> = {},
  required: string[] = [],
) => ({
  name,
  description,
  inputSchema: {
    type: "object",
    properties,
    required,
    additionalProperties: false,
  },
});
export const workspaceTools = [
  tool(
    "workspace_files",
    "List files in a workspace folder and get the current report text/hash. Start here to assess documents.",
    { path: { type: "string" } },
  ),
  tool(
    "workspace_read",
    "Read workspace-relative Word/PDF/email text, Excel cells or PowerPoint slide text. Read coverage warnings: Excel formulas are not recalculated and charts/layout are not assessed. Includes an exact hash for plain-text draft edits.",
    { path: { type: "string" } },
    ["path"],
  ),
  tool(
    "workspace_prepare_report",
    "Prepare an isolated report draft when the user asks to write or refine a report. Returns its current text and hash.",
  ),
  tool(
    "workspace_save_report",
    "Save the user's requested report using the exact current hash. Never changes original source documents.",
    { text: { type: "string" }, expectedHash: { type: "string" } },
    ["text", "expectedHash"],
  ),
  tool(
    "workspace_write_draft",
    "Edit a plain text/Markdown/CSV file only inside the conversation's existing isolated draft. Requires its exact previous hash, or empty hash for a new file.",
    {
      path: { type: "string" },
      text: { type: "string" },
      expectedHash: { type: "string" },
    },
    ["path", "text", "expectedHash"],
  ),
];
export const codeWorkspaceTools = [
  workspaceTools[0],
  workspaceTools[1],
  tool(
    "workspace_edit",
    "Create or replace one plain-text file in this code workspace. Read its current hash first; use an empty expectedHash for a new file. Returns the actual diff and new hash. Paths outside this workspace, hidden files, symlinks and credential files are blocked.",
    {
      path: { type: "string" },
      text: { type: "string" },
      expectedHash: { type: "string" },
    },
    ["path", "text", "expectedHash"],
  ),
  tool(
    "workspace_command",
    "Propose one terminal command for the selected code workspace. The exact command is displayed to the user and never runs until they tap Approve and run. Commands run as Termux and can access other Termux files, sign-ins and the network; they are not sandboxed. Prefer workspace_files/workspace_read for inspection and workspace_edit for file changes.",
    { command: { type: "string" } },
    ["command"],
  ),
];
export class WorkspaceTools {
  store: Store;
  busy = false;
  constructor(store: Store) {
    this.store = store;
  }
  async tool(
    id: string,
    name: string,
    input: any,
    active = () => true,
    allowWrites = true,
  ): Promise<unknown> {
    if (this.busy) throw new Error("Let the current document tool finish.");
    if (!active()) throw new Error("This request was stopped.");
    if (!input || typeof input !== "object" || Array.isArray(input))
      throw new Error("Invalid workspace request.");
    const c = this.store.conversation(id),
      project = this.store.project(c.projectId);
    if (["assistant", "meeting", "system"].includes(project.kind))
      throw new Error("Use the tools for this workspace.");
    if (!allowWrites && !["workspace_files", "workspace_read"].includes(name))
      throw new Error(
        "Quick answers and briefings are read-only. Use Full conversation to request changes.",
      );
    this.busy = true;
    try {
      if (name === "workspace_files")
        return {
          files: listFiles(c.workspace, input.path || ""),
          report: report(this.store, id),
          mode: c.mode,
        };
      if (name === "workspace_read") {
        const doc = await readDocument(c.workspace, input.path);
        return {
          ...doc,
          hash: doc.extracted
            ? undefined
            : digest(readFileSync(safePath(c.workspace, input.path))),
        };
      }
      if (name === "workspace_edit") {
        if (project.kind !== "code")
          throw new Error("Direct edits belong in a code workspace.");
        if (typeof input.path !== "string" || !input.path ||
            typeof input.text !== "string" || input.text.includes("\0") ||
            Buffer.byteLength(input.text) > 100_000 ||
            typeof input.expectedHash !== "string" ||
            !/^(?:[a-f0-9]{64})?$/.test(input.expectedHash))
          throw new Error("Provide a text file under 100 KB and its current hash.");
        const path = safePath(c.workspace, input.path);
        if (existsSync(path) && !lstatSync(path).isFile())
          throw new Error("Choose a regular text file.");
        const existed = existsSync(path);
        const mode = existed ? lstatSync(path).mode & 0o777 : 0o600;
        const before = existed ? readFileSync(path) : Buffer.alloc(0);
        if (before.includes(0)) throw new Error("This file is not plain text.");
        let beforeText: string;
        try { beforeText = new TextDecoder("utf-8", { fatal: true }).decode(before); }
        catch { throw new Error("This file is not UTF-8 text."); }
        const previousHash = existed ? digest(before) : "";
        if (previousHash !== input.expectedHash)
          throw new Error("The file changed. Read it again before editing.");
        if (!active()) throw new Error("This request was stopped.");
        mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
        const temporary = `${path}.galaxy-${randomUUID()}`;
        try {
          privateWrite(temporary, input.text);
          chmodSync(temporary, mode);
          if (!active()) throw new Error("This request was stopped.");
          renameSync(temporary, path);
        } finally {
          try { if (existsSync(temporary)) unlinkSync(temporary); } catch { /* no temporary file */ }
        }
        const diff = createPatch(input.path, beforeText, input.text);
        return { saved: true, path: input.path, hash: digest(input.text),
                 diff: diff.slice(0, 20_000), diffTruncated: diff.length > 20_000,
                 location: "code workspace" };
      }
      if (name === "workspace_prepare_report") {
        if (!active()) throw new Error("This request was stopped.");
        return await prepareReport(this.store, id);
      }
      if (name === "workspace_save_report") {
        if (!active()) throw new Error("This request was stopped.");
        return saveReport(this.store, id, input.text, input.expectedHash);
      }
      if (name === "workspace_write_draft") {
        if (c.mode !== "draft" || c.workspace === project.path)
          throw new Error(
            "Prepare an isolated draft before editing a source document.",
          );
        if (
          typeof input.path !== "string" ||
          !/\.(txt|md|csv|tsv|json)$/i.test(input.path)
        )
          throw new Error("Edit a plain-text draft file.");
        if (
          typeof input.text !== "string" ||
          !input.text.trim() ||
          Buffer.byteLength(input.text) > 100000 ||
          input.text.includes("\0")
        )
          throw new Error("Draft text must be nonempty and under 100 KB.");
        const path = safePath(c.workspace, input.path),
          before = existsSync(path) ? digest(readFileSync(path)) : "";
        if (before !== input.expectedHash)
          throw new Error(
            "The draft file changed. Read it again before editing.",
          );
        if (!active()) throw new Error("This request was stopped.");
        mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
        privateWrite(path, input.text);
        return {
          saved: true,
          path: input.path,
          hash: digest(input.text),
          location: "isolated draft",
        };
      }
      throw new Error("Unsupported workspace tool.");
    } finally {
      this.busy = false;
    }
  }
}

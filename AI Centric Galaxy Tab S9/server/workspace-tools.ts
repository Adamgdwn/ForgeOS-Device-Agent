import { existsSync, readFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
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
    "Read a workspace-relative document, including Word/PDF/email text. Includes an exact hash for plain-text draft edits.",
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
      throw new Error("Quick answers and briefings are read-only. Use Full conversation to request changes.");
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

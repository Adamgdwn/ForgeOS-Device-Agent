import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";
import { existsSync, readFileSync, statSync, rmSync } from "node:fs";
import { resolve, extname, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { ROOT, PORT, ORIGIN, TABLET_RUNTIME, readSettings } from "./config.ts";
import { Store, redact } from "./store.ts";
import { Auth } from "./auth.ts";
import { VoiceHandoff } from "./voice.ts";
import { AgentHost } from "./codex.ts";
import { ensureTabletWorkspace } from "./tablet.ts";
import { ensureAssistantWorkspace, assistantKind } from "./assistant.ts";
import { OneDrive } from "./onedrive.ts";
import { documentEntries, documentDownload } from "./documents.ts";
import { recovery, saveRecovery } from "./recovery.ts";
import {
  createCollection,
  createCodeWorkspace,
  stageUploads,
  installMaterials,
  materialReplay,
  type MaterialTarget,
} from "./materials.ts";
import {
  report,
  prepareReport,
  saveReport,
  makeExport,
  exportRecord,
  exportFile,
  formats,
} from "./reports.ts";
import {
  readDocument,
  createDraft,
  changes,
  applyLocalChange,
  checkpointDraft,
  digest,
} from "./files.ts";

async function body(req: IncomingMessage, limit = 30_000): Promise<any> {
  if (!req.headers["content-type"]?.startsWith("application/json"))
    throw new Error("Send JSON for this action.");
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > limit) throw new Error("Request is too large.");
    chunks.push(Buffer.from(chunk));
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
  } catch {
    throw new Error("Invalid request.");
  }
}
function string(value: unknown, max = 16_000): string {
  if (typeof value !== "string" || !value.trim() || value.length > max)
    throw new Error("A required field is missing or too long.");
  return value.trim();
}
function json(res: ServerResponse, data: unknown, status = 200) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(data));
}
export function application(
  store = new Store(),
  host = new AgentHost(store),
  drive = new OneDrive(store),
) {
  const auth = new Auth(store),
    locks = new Set<string>(),
    streams = new Set<ServerResponse>(),
    voice = new VoiceHandoff();
  store.recover();
  store.db
    .prepare(
      "UPDATE exports SET cloudState='uncertain' WHERE cloudState='pending'",
    )
    .run();
  const projectBusy = (projectId: string) =>
    !!host.active && store.conversation(host.active.id).projectId === projectId;
  const targetOf = (data: any): MaterialTarget => {
    const projectId = data.projectId ? string(data.projectId, 100) : undefined;
    if (projectId) store.project(projectId);
    if (projectId && store.project(projectId).kind === "system")
      throw new Error(
        "Use a document workspace to gather material. System is for the tablet.",
      );
    if (projectId && store.project(projectId).kind === "assistant")
      throw new Error(
        "Ask Assistant to save a named meeting brief first, then add material to that meeting workspace.",
      );
    const conversationId = data.conversationId
      ? string(data.conversationId, 100)
      : undefined;
    if (
      conversationId &&
      store.conversation(conversationId).projectId !== projectId
    )
      throw new Error("Choose a conversation in this workspace.");
    return {
      projectId,
      conversationId,
      name: projectId ? store.project(projectId).name : string(data.name, 80),
    };
  };
  if (!store.projects().length)
    store.addProject({
      name: "Meeting kit",
      path: resolve(ROOT, "examples/meeting-kit"),
      kind: "local",
      description: "Sample documents · try a folder assessment",
    });
  ensureTabletWorkspace(store);
  ensureAssistantWorkspace(store);
  const server = createServer(async (req, res) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("X-Frame-Options", "DENY");
    res.setHeader(
      "Permissions-Policy",
      "camera=(), microphone=(), geolocation=()",
    );
    res.setHeader(
      "Content-Security-Policy",
      "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    );
    try {
      auth.validateRequest(req);
      const url = new URL(req.url || "/", ORIGIN),
        path = url.pathname,
        method = req.method || "GET";
      if (path === "/api/session" && method === "GET") {
        json(res, {
          authenticated: auth.valid(req),
          runtime: TABLET_RUNTIME ? "tablet" : "workstation",
        });
        return;
      }
      if (path === "/api/session" && method === "POST") {
        auth.login(string((await body(req)).code, 200), res);
        json(res, { authenticated: true });
        return;
      }
      if (path === "/api/session/native" && method === "POST") {
        auth.loginNative(string((await body(req)).ticket, 100), res);
        json(res, { authenticated: true });
        return;
      }
      if (path.startsWith("/api/")) {
        if (!auth.valid(req)) {
          json(
            res,
            { error: "Reconnect this browser to your workspace to continue." },
            401,
          );
          return;
        }
        if (path === "/api/session" && method === "DELETE") {
          auth.logout(req, res);
          json(res, { ok: true });
          return;
        }
        if (path.startsWith("/api/voice/")) {
          if (!TABLET_RUNTIME || ORIGIN !== "http://localhost:4318")
            throw new Error("Talk is available in the tablet workspace.");
          const cookie = auth.cookie(req);
          if (path === "/api/voice/start" && method === "POST") {
            const data = await body(req);
            const [, kind, projectId, conversationId] = String(data.key).split(":");
            if (kind !== "chat" || (conversationId !== "new" &&
                store.conversation(conversationId).projectId !== projectId))
              throw new Error("Choose a conversation before using Talk.");
            if (recovery(store, data.key).revision !== data.revision)
              throw new Error("The draft changed. Tap Talk again.");
            json(res, voice.start(cookie, data.key, data.revision));
          }
          else if (path === "/api/voice/next" && method === "GET")
            json(res, voice.next(cookie));
          else if (path === "/api/voice/result" && method === "POST") {
            const result = await body(req, 10_000);
            json(res, voice.finish(cookie, result.id, result.status, result.text));
          } else if (path === "/api/voice/status" && method === "GET")
            json(res, voice.status(cookie, url.searchParams.get("id")));
          else if (path === "/api/voice/cancel" && method === "POST")
            json(res, voice.cancel(cookie, (await body(req)).id));
          else json(res, { error: "This voice action is unavailable." }, 404);
          return;
        }
        if (path === "/api/bootstrap" && method === "GET") {
          json(res, {
            runtime: TABLET_RUNTIME ? "tablet" : "workstation",
            instanceId: store.db
              .prepare("SELECT value FROM metadata WHERE key='instanceId'")
              .get()!.value,
            projects: store.projects(),
            conversations: store.conversations(),
            accounts: drive.accounts(),
            host: await host.status(),
            microsoftConfigured: !!readSettings().microsoftClientId,
          });
          return;
        }
        const submissionMatch = /^\/api\/submissions\/([\w-]+)$/.exec(path);
        if (path === "/api/recovery" && method === "GET") {
          json(res, recovery(store, url.searchParams.get("key")));
          return;
        }
        if (path === "/api/recovery" && method === "POST") {
          const data = await body(req, 2_000_000);
          json(res, saveRecovery(store, data.key, data.value, data.revision));
          return;
        }
        if (submissionMatch && method === "GET") {
          const submission = store.db
            .prepare("SELECT conversationId, state FROM submissions WHERE id=?")
            .get(submissionMatch[1]);
          json(res, { submission: submission || null });
          return;
        }
        if (path === "/api/tablet/status" && method === "GET") {
          json(res, await host.tablet.status());
          return;
        }
        if (path === "/api/tablet/actions" && method === "GET") {
          json(
            res,
            host.tablet.actions(
              string(url.searchParams.get("conversationId"), 100),
            ),
          );
          return;
        }
        const tabletAction = /^\/api\/tablet\/actions\/([0-9a-f-]+)$/.exec(
          path,
        );
        if (tabletAction && method === "POST") {
          if (host.active || locks.has("tablet-change"))
            throw new Error(
              "Let the current request finish before changing a tablet setting.",
            );
          const data = await body(req);
          if (host.active || locks.has("tablet-change"))
            throw new Error(
              "Let the current request finish before changing a tablet setting.",
            );
          locks.add("tablet-change");
          try {
            json(res, await host.tablet.decide(tabletAction[1], data.decision));
          } finally {
            locks.delete("tablet-change");
          }
          return;
        }
        if (path === "/api/accounts" && method === "GET") {
          json(res, drive.accounts());
          return;
        }
        if (path === "/api/accounts" && method === "POST") {
          json(res, drive.add());
          return;
        }
        if (path === "/api/workspaces" && method === "POST") {
          const data = await body(req);
          const name = string(data.name, 80);
          if (data.kind !== undefined && data.kind !== "code")
            throw new Error("Choose a supported workspace type.");
          json(
            res,
            data.kind === "code"
              ? createCodeWorkspace(store, name)
              : createCollection(store, name),
          );
          return;
        }
        if (path === "/api/materials" && method === "POST") {
          const data = await body(req, 35_000_000),
            target = targetOf(data);
          const fingerprint = digest(JSON.stringify(data)),
            id = string(data.id, 100);
          const replay = materialReplay(store, id, fingerprint);
          if (replay) {
            json(res, replay);
            return;
          }
          const key = `project:${target.projectId || "new"}`;
          if (
            locks.has("import") ||
            locks.has("export") ||
            locks.has(key) ||
            (target.conversationId && locks.has(target.conversationId)) ||
            (target.projectId && projectBusy(target.projectId))
          )
            throw new Error(
              "Let the current operation finish before adding material.",
            );
          locks.add(key);
          locks.add("import");
          let stage: string | undefined;
          try {
            stage = await stageUploads(data.files || [], data.email);
            const project = await installMaterials(store, stage, target);
            store.db
              .prepare("INSERT INTO material_batches VALUES (?,?,?)")
              .run(id, fingerprint, JSON.stringify(project));
            json(res, project);
          } finally {
            if (stage) rmSync(stage, { recursive: true, force: true });
            locks.delete(key);
            locks.delete("import");
          }
          return;
        }
        const exportMatch =
          /^\/api\/exports\/([0-9a-f-]{36})(?:\/(download|onedrive|device-receipt))?$/.exec(
            path,
          );
        if (exportMatch) {
          const row = exportRecord(store, exportMatch[1]);
          if (method === "POST" && exportMatch[2] === "device-receipt") {
            const data = await body(req);
            store.db
              .prepare(
                "UPDATE exports SET deviceDestination=?, deviceSavedAt=? WHERE id=?",
              )
              .run(
                string(data.destination, 2000),
                new Date().toISOString(),
                row.id,
              );
            json(res, { recorded: true });
            return;
          }
          if (method === "GET" && exportMatch[2] === "download") {
            res.setHeader("Content-Type", formats[row.format]);
            res.setHeader(
              "Content-Disposition",
              `attachment; filename="report.${row.format}"; filename*=UTF-8''${encodeURIComponent(row.filename)}`,
            );
            res.end(readFileSync(exportFile(row)));
            return;
          }
          if (method === "POST" && exportMatch[2] === "onedrive") {
            const data = await body(req);
            if (row.cloudState === "saved") {
              json(res, { webUrl: row.webUrl });
              return;
            }
            if (row.cloudState)
              throw new Error(
                "This export was already submitted. Check the chosen OneDrive folder before creating another export; it will not be retried automatically.",
              );
            if (!Number.isInteger(data.slot) || data.slot < 1 || data.slot > 3)
              throw new Error("Choose an account with upload access.");
            const name = string(data.name, 180);
            if (!name.toLowerCase().endsWith(`.${row.format}`))
              throw new Error(`Keep the .${row.format} filename extension.`);
            const parentId = string(data.parentId, 200),
              connectionId = string(data.connectionId, 100);
            const account = drive.accounts().find((a) => a.slot === data.slot);
            const destination = `${account?.username || account?.label || "Selected account"} / ${data.folderLabel ? string(data.folderLabel, 2000) : parentId} / ${name}`;
            store.db
              .prepare(
                "UPDATE exports SET cloudState='pending', destination=? WHERE id=?",
              )
              .run(destination, row.id);
            try {
              const receipt = await drive.publishNew(
                data.slot,
                parentId,
                name,
                readFileSync(exportFile(row)),
                connectionId,
              );
              store.db
                .prepare(
                  "UPDATE exports SET cloudState='saved', webUrl=? WHERE id=?",
                )
                .run(receipt.webUrl, row.id);
              store.event(row.conversationId, "notice", {
                text: `Exported new OneDrive file: ${name}\n${receipt.webUrl}`,
              });
              json(res, receipt);
            } catch (error) {
              store.db
                .prepare("UPDATE exports SET cloudState='uncertain' WHERE id=?")
                .run(row.id);
              throw new Error(
                `${(error as Error).message} This export was not retried. Check the destination before creating another export.`,
              );
            }
            return;
          }
        }
        const accountMatch =
          /^\/api\/accounts\/([1-4])\/(connect|disconnect|remove|files|preview)$/.exec(
            path,
          );
        if (accountMatch) {
          const slot = Number(accountMatch[1]);
          if (accountMatch[2] === "preview" && method === "GET") {
            if (locks.has("import"))
              throw new Error("Let the current document finish opening first.");
            locks.add("import");
            try {
              json(
                res,
                await drive.preview(
                  slot,
                  string(url.searchParams.get("item"), 1000),
                  string(url.searchParams.get("connection"), 100),
                ),
              );
            } finally {
              locks.delete("import");
            }
            return;
          }
          if (accountMatch[2] === "connect" && method === "POST") {
            const data = await body(req);
            json(res, await drive.connect(slot, string(data.label, 60)));
            return;
          }
          if (accountMatch[2] === "disconnect" && method === "POST") {
            await drive.disconnect(slot);
            json(res, { disconnected: true });
            return;
          }
          if (accountMatch[2] === "remove" && method === "POST") {
            await drive.remove(slot);
            json(res, { removed: true });
            return;
          }
          if (accountMatch[2] === "files" && method === "GET") {
            json(
              res,
              await drive.browse(
                slot,
                url.searchParams.get("item") || "root",
                url.searchParams.get("cursor") || undefined,
              ),
            );
            return;
          }
        }
        if (path === "/api/collections" && method === "POST") {
          if (locks.has("import"))
            throw new Error("A document import is already running.");
          const data = await body(req);
          if (
            !Array.isArray(data.items) ||
            data.items.some(
              (i: any) =>
                !Number.isInteger(i.slot) ||
                i.slot < 1 ||
                i.slot > 4 ||
                typeof i.itemId !== "string",
            )
          )
            throw new Error("Select valid OneDrive files.");
          const target = targetOf(data),
            key = `project:${target.projectId || "new"}`;
          const fingerprint = digest(JSON.stringify(data));
          if (data.id) {
            const replay = materialReplay(
              store,
              string(data.id, 100),
              fingerprint,
            );
            if (replay) {
              json(res, replay);
              return;
            }
          }
          if (
            locks.has("import") ||
            locks.has("export") ||
            locks.has(key) ||
            (target.conversationId && locks.has(target.conversationId)) ||
            (target.projectId && projectBusy(target.projectId))
          )
            throw new Error(
              "Let the current operation finish before adding material.",
            );
          locks.add("import");
          locks.add(key);
          try {
            const project = await drive.collect(
              target.name,
              data.items,
              target,
            );
            if (data.id)
              store.db
                .prepare("INSERT INTO material_batches VALUES (?,?,?)")
                .run(data.id, fingerprint, JSON.stringify(project));
            json(res, project);
          } finally {
            locks.delete("import");
            locks.delete(key);
          }
          return;
        }
        const projectMatch =
          /^\/api\/projects\/([^/]+)\/(files|preview|sources|download)$/.exec(
            path,
          );
        if (projectMatch && method === "GET") {
          const project = store.project(projectMatch[1]),
            relative = url.searchParams.get("path") || "";
          if (projectMatch[2] === "download") {
            const file = documentDownload(
              store,
              project,
              project.path,
              relative,
            );
            res.setHeader("Content-Type", file.type);
            res.setHeader(
              "Content-Disposition",
              `attachment; filename*=UTF-8''${encodeURIComponent(file.filename)}`,
            );
            res.end(file.bytes);
            return;
          }
          if (projectMatch[2] === "files")
            json(
              res,
              project.kind === "system"
                ? (await host.tablet.files(relative)).files
                : documentEntries(store, project, project.path, relative),
            );
          else if (projectMatch[2] === "sources")
            json(
              res,
              store.db
                .prepare(
                  "SELECT localName, slot, webUrl, originalName FROM imports WHERE projectId=?",
                )
                .all(project.id),
            );
          else {
            const source = store.db
              .prepare(
                "SELECT i.originalName, i.webUrl, COALESCE(a.label, 'Linked host account') AS label FROM imports i LEFT JOIN accounts a ON a.slot=i.slot WHERE i.projectId=? AND i.localName=?",
              )
              .get(project.id, relative.replace(/\.extracted\.txt$/, ""));
            json(res, {
              ...(project.kind === "system"
                ? await host.tablet.read(relative)
                : await readDocument(project.path, relative)),
              source,
            });
          }
          return;
        }
        if (path === "/api/conversations" && method === "POST") {
          json(
            res,
            store.createConversation(string((await body(req)).projectId, 100)),
          );
          return;
        }
        const conversationMatch =
          /^\/api\/conversations\/([^/]+)(?:\/(events|messages|stop|draft|changes|apply|save|answer|command|preview|files|download|report|export|exports))?$/.exec(
            path,
          );
        if (conversationMatch) {
          const id = conversationMatch[1],
            action = conversationMatch[2],
            c = store.conversation(id),
            project = store.project(c.projectId);
          if (action === "download" && method === "GET") {
            const file = documentDownload(
              store,
              project,
              c.workspace,
              url.searchParams.get("path") || "",
            );
            res.setHeader("Content-Type", file.type);
            res.setHeader(
              "Content-Disposition",
              `attachment; filename*=UTF-8''${encodeURIComponent(file.filename)}`,
            );
            res.end(file.bytes);
            return;
          }
          if (!action && method === "GET") {
            json(res, { conversation: c, events: store.events(id) });
            return;
          }
          if (action === "report" && method === "GET") {
            json(res, report(store, id));
            return;
          }
          if (action === "exports" && method === "GET") {
            json(
              res,
              store.db
                .prepare(
                  "SELECT * FROM exports WHERE conversationId=? ORDER BY rowid DESC LIMIT 100",
                )
                .all(id),
            );
            return;
          }
          if (action === "events" && method === "GET") {
            if (streams.size >= 12)
              throw new Error(
                "Too many open workspace tabs. Close an unused tab and reconnect.",
              );
            const raw =
              req.headers["last-event-id"] ||
              url.searchParams.get("after") ||
              "0";
            let after = Number(raw);
            if (!Number.isSafeInteger(after) || after < 0)
              throw new Error("Invalid event cursor.");
            res.writeHead(200, {
              "Content-Type": "text/event-stream",
              Connection: "keep-alive",
              "X-Accel-Buffering": "no",
            });
            // An idle conversation has nothing to replay. Send the opening frame
            // immediately so EventSource doesn't wait for the ten-second heartbeat.
            res.write("retry: 1000\n: connected\n\n");
            streams.add(res);
            const send = (event: any) => {
              if (event.seq > after) {
                after = event.seq;
                res.write(
                  `id: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`,
                );
              }
            };
            let page;
            do {
              page = store.events(id, after);
              for (const event of page) send(event);
            } while (page.length === 1000);
            store.bus.on(id, send);
            const heartbeat = setInterval(
              () => res.write(": heartbeat\n\n"),
              10_000,
            );
            const expiry = setTimeout(() => res.end(), 25_000);
            res.on("close", () => {
              clearInterval(heartbeat);
              clearTimeout(expiry);
              store.bus.off(id, send);
              streams.delete(res);
            });
            return;
          }
          if (action === "files" && method === "GET") {
            json(
              res,
              project.kind === "system"
                ? (await host.tablet.files(url.searchParams.get("path") || ""))
                    .files
                : documentEntries(
                    store,
                    project,
                    c.workspace,
                    url.searchParams.get("path") || "",
                  ),
            );
            return;
          }
          if (action === "preview" && method === "GET") {
            const file = url.searchParams.get("path") || "";
            const source = store.db
              .prepare(
                "SELECT i.originalName, i.webUrl, COALESCE(a.label, 'Linked host account') AS label FROM imports i LEFT JOIN accounts a ON a.slot=i.slot WHERE i.projectId=? AND i.localName=?",
              )
              .get(c.projectId, file.replace(/\.extracted\.txt$/, ""));
            json(res, {
              ...(project.kind === "system"
                ? await host.tablet.read(file)
                : await readDocument(c.workspace, file)),
              source,
            });
            return;
          }
          if (action === "changes" && method === "GET") {
            if (assistantKind(project.kind)) {
              json(res, []);
              return;
            }
            const readOnlyFiles = new Set(
              store.db
                .prepare(
                  "SELECT localName FROM imports WHERE projectId=? AND slot=4",
                )
                .all(project.id)
                .map((row) => row.localName),
            );
            json(
              res,
              (await changes(c, project)).map((change) => ({
                ...change,
                readOnly: readOnlyFiles.has(change.path),
                cloudSource: !!store.db
                  .prepare(
                    "SELECT 1 FROM imports WHERE projectId=? AND localName=?",
                  )
                  .get(project.id, change.path),
              })),
            );
            return;
          }
          if (method === "POST") {
            const data = await body(
              req,
              action === "report" ? 600_000 : 30_000,
            );
            if (action === "messages") {
              if (locks.has("tablet-change") && project.kind === "system")
                throw new Error(
                  "A tablet setting is being verified. Try again shortly.",
                );
              if (locks.has(id) || locks.has(`project:${project.id}`))
                throw new Error(
                  "The workspace is updating. Try again shortly.",
                );
              const message = string(data.text),
                submissionId = string(data.id, 100);
              const health = await host.status();
              if (locks.has("tablet-change") && project.kind === "system")
                throw new Error(
                  "A tablet setting is being verified. Try again shortly.",
                );
              if (locks.has(id) || locks.has(`project:${project.id}`))
                throw new Error(
                  "The workspace is updating. Try again shortly.",
                );
              if (!health.compatible)
                throw new Error(
                  `This pilot expects ${health.expected}. Check the installed Codex version before continuing.`,
                );
              json(
                res,
                await host.submit(id, submissionId, message, data.replyStyle),
              );
              return;
            }
            if (action === "stop") {
              await host.stop(id);
              json(res, { stopped: true });
              return;
            }
            if (action === "answer") {
              await host.answer(
                id,
                string(data.requestId, 100),
                data.answers || {},
              );
              json(res, { answered: true });
              return;
            }
            if (action === "command") {
              if (project.kind !== "code")
                throw new Error("Choose a code workspace for commands.");
              await host.resolveCommand(
                id,
                string(data.requestId, 100),
                data.decision,
              );
              json(res, { resolved: true });
              return;
            }
            if (
              ["draft", "apply", "save", "report", "export"].includes(action)
            ) {
              if (
                assistantKind(project.kind) &&
                ["draft", "apply", "save"].includes(action)
              )
                throw new Error(
                  "Meeting briefs save directly in their meeting workspace. Use Report to edit or export a copy.",
                );
              if (project.kind === "system")
                throw new Error(
                  "Use the tablet change cards in System. Reports and document drafts belong in a document workspace.",
                );
              if (
                host.active?.id === id ||
                locks.has(id) ||
                locks.has(`project:${project.id}`)
              )
                throw new Error(
                  "Let the current operation finish before changing or saving this workspace.",
                );
              locks.add(id);
              try {
                if (action === "report") {
                  json(
                    res,
                    data.text !== undefined
                      ? saveReport(store, id, data.text, data.hash, data.path)
                      : await prepareReport(
                          store,
                          id,
                          data.path ? string(data.path, 300) : undefined,
                        ),
                  );
                } else if (action === "export") {
                  if (locks.has("export") || locks.has("import"))
                    throw new Error(
                      "Another report is being exported. Try again shortly.",
                    );
                  locks.add("export");
                  try {
                    json(
                      res,
                      await makeExport(
                        store,
                        id,
                        string(data.format, 10),
                        string(data.hash, 100),
                      ),
                    );
                  } finally {
                    locks.delete("export");
                  }
                } else if (action === "draft") {
                  if (c.mode === "draft") {
                    json(res, c);
                    return;
                  }
                  const workspace = await createDraft(project, id);
                  const updated = store.update(id, {
                    workspace,
                    mode: "draft",
                  });
                  store.event(id, "notice", {
                    text: "Draft workspace created from the current files. Requested edits will be made here; originals change only when you save a reviewed file.",
                  });
                  json(res, updated);
                } else {
                  if (c.mode !== "draft")
                    throw new Error("Start a draft before saving changes.");
                  const file = string(data.path, 1000);
                  const change = (await changes(c, project)).find(
                    (ch) => ch.path === file,
                  );
                  if (!change?.applicable)
                    throw new Error(
                      "This file has no supported draft change to save.",
                    );
                  if (action === "apply") {
                    if (
                      store.db
                        .prepare(
                          "SELECT 1 FROM imports WHERE projectId=? AND localName=?",
                        )
                        .get(project.id, file)
                    )
                      throw new Error(
                        "Use OneDrive save for imported originals, or export a new report copy.",
                      );
                    await applyLocalChange(c, project, file);
                  } else {
                    await drive.save(project.id, c.workspace, file);
                    await checkpointDraft(c.workspace, file);
                  }
                  store.event(id, "saved", {
                    path: file,
                    destination:
                      action === "apply" ? "local folder" : "OneDrive",
                    diff: change.diff,
                  });
                  json(res, { saved: true });
                }
              } finally {
                locks.delete(id);
              }
              return;
            }
          }
        }
        json(res, { error: "This action is not available." }, 404);
        return;
      }
      if (method !== "GET") {
        json(res, { error: "Method not allowed." }, 405);
        return;
      }
      const dist = resolve(ROOT, "dist");
      const file = resolve(
        dist,
        `.${decodeURIComponent(path === "/" ? "/index.html" : path)}`,
      );
      if (
        !file.startsWith(dist + sep) ||
        !existsSync(file) ||
        !statSync(file).isFile()
      ) {
        res.writeHead(404);
        res.end(
          "Build the app with npm run build before opening Galaxy Workspace.",
        );
        return;
      }
      const mime: Record<string, string> = {
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".webmanifest": "application/manifest+json",
      };
      res.setHeader(
        "Content-Type",
        mime[extname(file)] || "application/octet-stream",
      );
      res.end(readFileSync(file));
    } catch (error) {
      if (!res.headersSent)
        json(
          res,
          {
            error: redact(
              error instanceof Error
                ? error.message
                : "The request could not be completed.",
            ),
          },
          400,
        );
      else res.end();
    }
  });
  return {
    server,
    store,
    host,
    drive,
    close: async () => {
      for (const res of streams) res.end();
      drive.close();
      await host.close();
      await new Promise<void>((done) => server.close(() => done()));
      store.close();
    },
  };
}
if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  process.umask(0o077);
  const app = application();
  app.server.listen(PORT, "127.0.0.1", () =>
    console.log(
      `Galaxy Workspace listening at ${ORIGIN}. Run npm run pair locally for the pairing code.`,
    ),
  );
  let closing = false;
  const shutdown = async () => {
    if (closing) return;
    closing = true;
    await app.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

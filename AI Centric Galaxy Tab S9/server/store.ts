import { DatabaseSync } from "node:sqlite";
import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { mkdirSync } from "node:fs";
import { STATE } from "./config.ts";

export type Project = {
  id: string;
  name: string;
  path: string;
  kind: "local" | "onedrive" | "system" | "assistant" | "meeting" | "code";
  description: string;
};
export type Conversation = {
  id: string;
  projectId: string;
  title: string;
  threadId: string | null;
  workspace: string;
  mode: "explore" | "draft";
  status: string;
  turnId: string | null;
  createdAt: string;
  updatedAt: string;
};
export type Event = {
  seq: number;
  conversationId: string;
  type: string;
  data: any;
  createdAt: string;
};
export function redact(text: string): string {
  return text
    .replace(
      /\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b/g,
      "[redacted credential]",
    )
    .replace(/(authorization\s*[:=]\s*bearer\s+)[^\s"']+/gi, "$1[redacted]")
    .replace(
      /((?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password)\s*["']?\s*[:=]\s*["']?)[^\s,"'\n]+/gi,
      "$1[redacted]",
    );
}
export class Store {
  db: DatabaseSync;
  bus = new EventEmitter();
  constructor(path = resolve(STATE, "galaxy.sqlite")) {
    this.db = new DatabaseSync(path);
    this.db
      .exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, description TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, projectId TEXT NOT NULL REFERENCES projects(id), title TEXT NOT NULL, threadId TEXT, workspace TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, turnId TEXT, createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, conversationId TEXT NOT NULL REFERENCES conversations(id), type TEXT NOT NULL, data TEXT NOT NULL, createdAt TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS events_conversation ON events(conversationId, seq);
      CREATE TABLE IF NOT EXISTS submissions (id TEXT PRIMARY KEY, conversationId TEXT NOT NULL REFERENCES conversations(id), text TEXT NOT NULL, state TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS recovery (key TEXT PRIMARY KEY, value TEXT NOT NULL, revision INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS accounts (slot INTEGER PRIMARY KEY CHECK(slot BETWEEN 1 AND 3), label TEXT NOT NULL, homeId TEXT, username TEXT, status TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS imports (projectId TEXT NOT NULL REFERENCES projects(id), localName TEXT NOT NULL, slot INTEGER NOT NULL, driveId TEXT NOT NULL, itemId TEXT NOT NULL, etag TEXT NOT NULL, webUrl TEXT NOT NULL, originalName TEXT NOT NULL, homeId TEXT NOT NULL, PRIMARY KEY(projectId, localName));
      CREATE TABLE IF NOT EXISTS material_batches (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS reports (conversationId TEXT PRIMARY KEY REFERENCES conversations(id), path TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS exports (id TEXT PRIMARY KEY, conversationId TEXT NOT NULL REFERENCES conversations(id), filename TEXT NOT NULL, format TEXT NOT NULL, hash TEXT NOT NULL, cloudState TEXT NOT NULL DEFAULT '', webUrl TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS tablet_actions (id TEXT PRIMARY KEY, conversationId TEXT NOT NULL REFERENCES conversations(id), serial TEXT NOT NULL, setting TEXT NOT NULL, beforeValue TEXT NOT NULL, afterValue TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL, createdAt INTEGER NOT NULL, result TEXT NOT NULL);
    `);
    this.db
      .prepare("INSERT OR IGNORE INTO metadata VALUES ('instanceId', ?)")
      .run(randomUUID());
    const exportColumns = new Set(
      this.db
        .prepare("PRAGMA table_info(exports)")
        .all()
        .map((c) => c.name),
    );
    for (const [name, type] of Object.entries({
      createdAt: "TEXT NOT NULL DEFAULT ''",
      destination: "TEXT NOT NULL DEFAULT ''",
      deviceDestination: "TEXT NOT NULL DEFAULT ''",
      deviceSavedAt: "TEXT NOT NULL DEFAULT ''",
    }))
      if (!exportColumns.has(name))
        this.db.exec(`ALTER TABLE exports ADD COLUMN ${name} ${type}`);
    for (let slot = 1; slot <= 3; slot++)
      this.db
        .prepare("INSERT OR IGNORE INTO accounts VALUES (?, ?, NULL, NULL, ?)")
        .run(slot, `OneDrive ${slot}`, "disconnected");
  }
  projects(): Project[] {
    return this.db
      .prepare(
        "SELECT * FROM projects ORDER BY CASE WHEN kind='assistant' THEN 0 WHEN kind='system' THEN 1 ELSE 2 END, name",
      )
      .all() as Project[];
  }
  project(id: string): Project {
    const p = this.db.prepare("SELECT * FROM projects WHERE id=?").get(id) as
      Project | undefined;
    if (!p) throw new Error("Workspace not found.");
    return p;
  }
  addProject(project: Omit<Project, "id">): Project {
    const existing = this.db
      .prepare("SELECT * FROM projects WHERE path=?")
      .get(project.path) as Project | undefined;
    if (existing) return existing;
    const p = { id: randomUUID(), ...project };
    this.db
      .prepare("INSERT INTO projects VALUES (?, ?, ?, ?, ?)")
      .run(p.id, p.name, p.path, p.kind, p.description);
    return p;
  }
  conversations(): Conversation[] {
    return this.db
      .prepare("SELECT * FROM conversations ORDER BY updatedAt DESC")
      .all() as Conversation[];
  }
  conversation(id: string): Conversation {
    const c = this.db
      .prepare("SELECT * FROM conversations WHERE id=?")
      .get(id) as Conversation | undefined;
    if (!c) throw new Error("Conversation not found.");
    return c;
  }
  createConversation(projectId: string): Conversation {
    const p = this.project(projectId),
      now = new Date().toISOString();
    const c: Conversation = {
      id: randomUUID(),
      projectId,
      title: "New conversation",
      threadId: null,
      workspace: p.path,
      mode: "explore",
      status: "idle",
      turnId: null,
      createdAt: now,
      updatedAt: now,
    };
    if (p.kind === "assistant" || p.kind === "meeting") {
      if (p.kind === "assistant") {
        c.workspace = resolve(STATE, "meetings", `${now.slice(0, 10)}-${c.id}`);
        mkdirSync(c.workspace, { recursive: true, mode: 0o700 });
      }
      c.mode = "draft";
    }
    this.db
      .prepare(
        "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      )
      .run(
        c.id,
        c.projectId,
        c.title,
        c.threadId,
        c.workspace,
        c.mode,
        c.status,
        c.turnId,
        c.createdAt,
        c.updatedAt,
      );
    if (p.kind === "assistant" || p.kind === "meeting")
      this.db
        .prepare("INSERT INTO reports VALUES (?, ?)")
        .run(c.id, "Reports/Meeting brief.md");
    return c;
  }
  update(id: string, changes: Partial<Conversation>) {
    const c = {
      ...this.conversation(id),
      ...changes,
      updatedAt: new Date().toISOString(),
    };
    this.db
      .prepare(
        "UPDATE conversations SET projectId=?, title=?, threadId=?, workspace=?, mode=?, status=?, turnId=?, updatedAt=? WHERE id=?",
      )
      .run(
        c.projectId,
        c.title,
        c.threadId,
        c.workspace,
        c.mode,
        c.status,
        c.turnId,
        c.updatedAt,
        id,
      );
    return c;
  }
  event(id: string, type: string, data: unknown): Event {
    const createdAt = new Date().toISOString(),
      encoded = JSON.stringify(data, (_key, value) =>
        typeof value === "string" ? redact(value).slice(0, 200_000) : value,
      );
    const result = this.db
      .prepare(
        "INSERT INTO events(conversationId,type,data,createdAt) VALUES (?,?,?,?)",
      )
      .run(id, type, encoded, createdAt);
    const event = {
      seq: Number(result.lastInsertRowid),
      conversationId: id,
      type,
      data: JSON.parse(encoded),
      createdAt,
    };
    this.bus.emit(id, event);
    return event;
  }
  events(id: string, after = 0): Event[] {
    return this.db
      .prepare(
        "SELECT * FROM events WHERE conversationId=? AND seq>? ORDER BY seq LIMIT 1000",
      )
      .all(id, after)
      .map((e: any) => ({ ...e, data: JSON.parse(e.data) }));
  }
  recover() {
    this.db
      .prepare(
        "UPDATE tablet_actions SET status='uncertain', result='Host restarted before the result was confirmed. Check the tablet; this change will not be retried.' WHERE status IN ('applying','undoing')",
      )
      .run();
    for (const c of this.conversations())
      if (["running", "starting", "stopping", "waiting"].includes(c.status)) {
        const pending = new Set<string>();
        const commandEvents = this.db.prepare(
          "SELECT type, data FROM events WHERE conversationId=? AND type IN ('command-proposal','command-resolved') ORDER BY seq",
        ).all(c.id) as { type: string; data: string }[];
        for (const row of commandEvents) {
          const requestId = JSON.parse(row.data).requestId;
          if (row.type === "command-proposal") pending.add(requestId);
          else pending.delete(requestId);
        }
        for (const requestId of pending)
          this.event(c.id, "command-resolved", { requestId, decision: "interrupted" });
        this.update(c.id, { status: "interrupted", turnId: null });
        this.event(c.id, "status", {
          status: "interrupted",
          message:
            "Host service restarted. The previous request was not restarted. Review the saved activity before continuing.",
        });
      }
    this.db
      .prepare(
        "UPDATE submissions SET state='interrupted' WHERE state='pending'",
      )
      .run();
    this.db
      .prepare(
        "UPDATE accounts SET status=CASE WHEN homeId IS NULL THEN 'disconnected' ELSE 'connected' END WHERE status='connecting'",
      )
      .run();
  }
  close() {
    this.db.close();
  }
}

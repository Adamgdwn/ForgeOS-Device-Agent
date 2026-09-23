import { randomBytes, createHash, timingSafeEqual } from "node:crypto";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { STATE, ORIGIN, TABLET_RUNTIME, privateWrite } from "./config.ts";
import type { Store } from "./store.ts";

const hash = (s: string) => createHash("sha256").update(s).digest("hex");
export const PAIR_FILE = resolve(STATE, "pairing-code");
export const NATIVE_TICKET_FILE = resolve(STATE, "native-pair-ticket.json");
export function rotatePairCode() {
  privateWrite(PAIR_FILE, randomBytes(18).toString("base64url"));
}
if (!existsSync(PAIR_FILE)) rotatePairCode();
export class Auth {
  store: Store;
  attempts: number[] = [];
  constructor(store: Store) {
    this.store = store;
  }
  validateRequest(req: IncomingMessage) {
    if (req.headers.host !== new URL(ORIGIN).host)
      throw new Error("Host is not configured for this workspace.");
    if (req.headers.origin && req.headers.origin !== ORIGIN)
      throw new Error("Request origin is not allowed.");
    if (
      req.method !== "GET" &&
      (req.headers.origin !== ORIGIN || req.headers["x-galaxy-request"] !== "1")
    )
      throw new Error("Request origin is not allowed.");
  }
  cookie(req: IncomingMessage) {
    return (
      /(?:^|;\s*)galaxy_session=([\w-]+)/.exec(req.headers.cookie || "")?.[1] ||
      ""
    );
  }
  valid(req: IncomingMessage) {
    return !!this.store.db
      .prepare("SELECT hash FROM sessions WHERE hash=? AND expires>?")
      .get(hash(this.cookie(req)), Date.now());
  }
  login(code: string, res: ServerResponse) {
    const now = Date.now();
    this.attempts = this.attempts.filter((time) => time > now - 5 * 60_000);
    if (this.attempts.length >= 10)
      throw new Error("Too many pairing attempts. Try again in five minutes.");
    this.attempts.push(now);
    if (
      !timingSafeEqual(
        Buffer.from(hash(code.trim())),
        Buffer.from(hash(readFileSync(PAIR_FILE, "utf8").trim())),
      )
    )
      throw new Error("That pairing code did not match.");
    this.issueSession(res);
  }
  loginNative(ticket: string, res: ServerResponse) {
    if (!TABLET_RUNTIME || ORIGIN !== "http://localhost:4318")
      throw new Error("Local recovery is unavailable.");
    const saved = existsSync(NATIVE_TICKET_FILE)
      ? JSON.parse(readFileSync(NATIVE_TICKET_FILE, "utf8"))
      : null;
    if (
      !saved ||
      saved.expires < Date.now() ||
      !/^[a-f0-9]{64}$/.test(saved.hash) ||
      !timingSafeEqual(Buffer.from(hash(ticket)), Buffer.from(saved.hash))
    )
      throw new Error("Recovery expired. Use Reconnect this tablet again.");
    rmSync(NATIVE_TICKET_FILE);
    this.issueSession(res);
  }
  private issueSession(res: ServerResponse) {
    const now = Date.now(),
      token = randomBytes(32).toString("base64url");
    this.store.db.prepare("DELETE FROM sessions WHERE expires<=?").run(now);
    this.store.db
      .prepare("INSERT INTO sessions VALUES (?, ?)")
      .run(hash(token), now + 7 * 24 * 60 * 60_000);
    res.setHeader(
      "Set-Cookie",
      `galaxy_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800${
        ORIGIN.startsWith("https:") ? "; Secure" : ""
      }`,
    );
  }
  logout(req: IncomingMessage, res: ServerResponse) {
    this.store.db
      .prepare("DELETE FROM sessions WHERE hash=?")
      .run(hash(this.cookie(req)));
    res.setHeader(
      "Set-Cookie",
      "galaxy_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
    );
  }
}

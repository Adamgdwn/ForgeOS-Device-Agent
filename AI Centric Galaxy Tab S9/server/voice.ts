import { createHash, randomUUID } from "node:crypto";

type VoiceState = "waiting" | "listening" | "complete" | "canceled" | "error";
type Session = { id: string; key: string; revision: number; state: VoiceState; text: string; expires: number };

/** One short-lived dictation handoff per authenticated browser session. */
export class VoiceHandoff {
  private sessions = new Map<string, Session>();
  private owner(cookie: string) {
    return createHash("sha256").update(cookie).digest("hex");
  }
  private current(cookie: string) {
    const owner = this.owner(cookie);
    const session = this.sessions.get(owner);
    if (session && session.expires <= Date.now()) {
      this.sessions.delete(owner);
      return null;
    }
    return session || null;
  }
  start(cookie: string, key: unknown, revision: unknown) {
    if (typeof key !== "string" || key.length < 1 || key.length > 250 || !/^[\w:-]+$/.test(key))
      throw new Error("Choose a conversation before using Talk.");
    if (!Number.isSafeInteger(revision) || Number(revision) < 0)
      throw new Error("Save the draft before using Talk.");
    const session: Session = {
      id: randomUUID(), key, revision: Number(revision), state: "waiting", text: "", expires: Date.now() + 90_000,
    };
    this.sessions.set(this.owner(cookie), session);
    return { id: session.id };
  }
  next(cookie: string) {
    const session = this.current(cookie);
    if (!session || session.state !== "waiting") return { id: null };
    session.state = "listening";
    return { id: session.id };
  }
  finish(cookie: string, id: unknown, status: unknown, text: unknown) {
    const session = this.current(cookie);
    if (!session || session.id !== id || session.state !== "listening")
      throw new Error("That voice request is no longer active.");
    if (status === "complete") {
      if (typeof text !== "string" || !text.trim() || text.length > 5000)
        throw new Error("No usable speech was returned.");
      session.text = text.trim();
      session.state = "complete";
    } else if (status === "canceled" || status === "error") {
      session.state = status;
    } else throw new Error("Invalid voice result.");
    session.expires = Date.now() + 60_000;
    return { ok: true };
  }
  status(cookie: string, id: unknown) {
    const session = this.current(cookie);
    if (!session || session.id !== id) return { state: "expired" };
    const result = { state: session.state, key: session.key, revision: session.revision, text: session.text };
    if (["complete", "canceled", "error"].includes(session.state))
      this.sessions.delete(this.owner(cookie));
    return result;
  }
  cancel(cookie: string, id: unknown) {
    const session = this.current(cookie);
    if (session?.id === id) this.sessions.delete(this.owner(cookie));
    return { ok: true };
  }
}

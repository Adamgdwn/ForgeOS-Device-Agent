/** Insert recognized words at the selection captured when Talk was pressed. */
export function insertTranscript(text: string, start: number, end: number, transcript: string) {
  const from = Math.max(0, Math.min(text.length, start));
  const to = Math.max(from, Math.min(text.length, end));
  const before = text.slice(0, from), after = text.slice(to);
  const left = before && !/\s$/.test(before) ? " " : "";
  const right = after && !/^\s/.test(after) ? " " : "";
  const inserted = before + left + transcript.trim() + right;
  const next = inserted + after;
  if (next.length > 14000) throw new Error("That transcript is too long for this message.");
  return { text: next, caret: inserted.length };
}
export function nativeVoiceAvailable(userAgent: string, origin: string): boolean {
  if (origin !== "http://localhost:4318") return false;
  const version = /(?:^|\s)GalaxyWorkspace\/(\d+)\.(\d+)\.(\d+)/.exec(userAgent);
  if (!version) return false;
  const [, major, minor, patch] = version.map(Number);
  return major > 0 || minor > 4 || (minor === 4 && patch >= 1);
}

// The local engine confirms durable SQLite recovery; browser storage is a fallback.
import { validRecovery, type Draft } from "../shared/recovery.ts";
export {
  emptyChat,
  type ChatDraft,
  type ReportDraft,
  type Submission,
} from "../shared/recovery.ts";
type Snapshot = {
  value: Draft | null;
  error: string;
  saving: boolean;
  ready: boolean;
};
const cache = new Map<string, Snapshot>();
const listeners = new Set<() => void>();
const loads = new Map<string, Promise<void>>(),
  saves = new Map<string, Promise<void>>();
const versions = new Map<string, number>();
export const recoveryRevision = (key: string) => versions.get(key);
const prefix = "galaxy-recovery-v1:";
const enabled = () => typeof window !== "undefined";
const notify = () => {
  for (const listener of listeners) listener();
};
function browserCopy(key: string, value: Draft | null) {
  if (value) localStorage.setItem(prefix + key, JSON.stringify(value));
  else localStorage.removeItem(prefix + key);
}
export function recoverySnapshot(key: string): Snapshot {
  if (!cache.has(key)) {
    try {
      const raw = localStorage.getItem(prefix + key),
        value = raw ? JSON.parse(raw) : null;
      if (value !== null && !validRecovery(value))
        throw new Error("Invalid recovery copy");
      cache.set(key, { value, error: "", saving: false, ready: !enabled() });
    } catch {
      cache.set(key, {
        value: null,
        error:
          "Could not read the browser recovery copy. Checking the workspace copy…",
        saving: false,
        ready: !enabled(),
      });
    }
  }
  return cache.get(key)!;
}
export async function hydrateRecovery(key: string): Promise<void> {
  if (!enabled() || key.startsWith("opening:")) return;
  if (loads.has(key)) return loads.get(key);
  const original = recoverySnapshot(key);
  const loading = (async () => {
    try {
      const response = await fetch(
        `/api/recovery?key=${encodeURIComponent(key)}`,
        { signal: AbortSignal.timeout(8000) },
      );
      if (!response.ok) throw new Error();
      const result = await response.json();
      if (result.value !== null && !validRecovery(result.value))
        throw new Error();
      versions.set(key, result.revision);
      if (cache.get(key) === original && !original.saving) {
        const value = result.found ? result.value : original.value;
        cache.set(key, { value, error: "", saving: false, ready: true });
        try {
          browserCopy(key, value);
        } catch {
          /* SQLite remains authoritative. */
        }
        if (!result.found && value)
          queueMicrotask(() => writeRecovery(key, value));
      } else cache.set(key, { ...recoverySnapshot(key), ready: true });
    } catch {
      cache.set(key, {
        ...recoverySnapshot(key),
        ready: true,
        error:
          "Recovery could not be checked with the workspace. Keep this screen open and copy or save your text before leaving.",
      });
    }
    notify();
  })();
  loads.set(key, loading);
  return loading;
}
function persist(key: string): Promise<void> {
  if (saves.has(key)) return saves.get(key)!;
  const saving = (async () => {
    await hydrateRecovery(key);
    while (recoverySnapshot(key).saving) {
      const snapshot = recoverySnapshot(key);
      try {
        if (!versions.has(key))
          throw new Error(
            "Recovery is unavailable. Keep this screen open until you save or copy the text.",
          );
        const response = await fetch("/api/recovery", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Galaxy-Request": "1",
          },
          body: JSON.stringify({
            key,
            value: snapshot.value,
            revision: versions.get(key),
          }),
          signal: AbortSignal.timeout(8000),
        });
        const result = await response.json();
        if (!response.ok)
          throw new Error(
            result.error ||
              "Recovery could not be saved. Keep this screen open and save or copy your text.",
          );
        versions.set(key, result.revision);
        if (cache.get(key) === snapshot)
          cache.set(key, {
            ...snapshot,
            saving: false,
            error: "",
            ready: true,
          });
      } catch (error) {
        cache.set(key, {
          ...recoverySnapshot(key),
          saving: false,
          error: (error as Error).message,
        });
      }
      notify();
    }
  })().finally(() => saves.delete(key));
  saves.set(key, saving);
  return saving;
}
export function writeRecovery(key: string, value: Draft | null): boolean {
  let error = "";
  if (value !== null && !validRecovery(value)) return false;
  const previous = recoverySnapshot(key);
  try {
    browserCopy(key, value);
  } catch {
    error =
      "Browser recovery is unavailable. Keep this screen open until the workspace confirms the save.";
  }
  cache.set(key, { value, error, saving: enabled(), ready: previous.ready });
  notify();
  if (enabled()) void persist(key);
  return !error || enabled();
}
export async function flushRecovery(key: string) {
  if (enabled()) await persist(key);
  if (recoverySnapshot(key).error) throw new Error(recoverySnapshot(key).error);
}
export function subscribeRecovery(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export function invalidateRecovery(key?: string) {
  if (key) {
    cache.delete(key);
    loads.delete(key);
    versions.delete(key);
  } else {
    cache.clear();
    loads.clear();
    versions.clear();
  }
  notify();
}
if (enabled())
  window.addEventListener("storage", (event) => {
    // Another browser tab must not silently replace an active editor.
    if (event.key?.startsWith(prefix)) {
      const key = event.key.slice(prefix.length);
      if (!cache.has(key)) invalidateRecovery(key);
    }
  });

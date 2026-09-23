import type { Store } from "./store.ts";
import { validRecovery } from "../shared/recovery.ts";
function validKey(store: Store, key: unknown) {
  if (typeof key !== "string" || key.length > 200)
    throw new Error("Invalid recovery workspace.");
  const [instance, kind, projectOrConversation, conversation, ...extra] =
    key.split(":");
  if (
    instance !==
      store.db
        .prepare("SELECT value FROM metadata WHERE key='instanceId'")
        .get()!.value ||
    extra.length ||
    !["chat", "report"].includes(kind)
  )
    throw new Error("Invalid recovery workspace.");
  if (kind === "chat") {
    store.project(projectOrConversation);
    if (conversation !== "new") store.conversation(conversation);
  } else {
    if (conversation !== undefined)
      throw new Error("Invalid recovery workspace.");
    if (
      !store.db
        .prepare(
          "SELECT 1 FROM conversations WHERE id=? UNION SELECT 1 FROM projects WHERE id=?",
        )
        .get(projectOrConversation, projectOrConversation)
    )
      throw new Error("Invalid recovery workspace.");
  }
  return key;
}
export function recovery(store: Store, input: unknown) {
  const key = validKey(store, input);
  const row = store.db
    .prepare("SELECT value, revision FROM recovery WHERE key=?")
    .get(key);
  return {
    found: !!row,
    value: row ? JSON.parse(String(row.value)) : null,
    revision: Number(row?.revision || 0),
  };
}
export function saveRecovery(
  store: Store,
  input: unknown,
  value: unknown,
  revision: unknown,
) {
  const key = validKey(store, input);
  if (
    value !== null &&
    (!validRecovery(value) || key.split(":")[1] !== value.kind)
  )
    throw new Error("Invalid recovery copy.");
  if (!Number.isSafeInteger(revision) || Number(revision) < 0)
    throw new Error("Invalid recovery version.");
  const current = recovery(store, key);
  if (current.revision !== revision)
    throw new Error(
      "This recovery copy changed in another view. Your text is kept here; copy it before reloading to compare the saved recovery.",
    );
  store.db
    .prepare(
      "INSERT INTO recovery VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, revision=excluded.revision",
    )
    .run(key, JSON.stringify(value), current.revision + 1);
  return { revision: current.revision + 1 };
}

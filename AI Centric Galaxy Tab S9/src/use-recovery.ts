import { useEffect, useSyncExternalStore } from "react";
import {
  recoverySnapshot,
  subscribeRecovery,
  writeRecovery,
  hydrateRecovery,
  type ChatDraft,
  type ReportDraft,
} from "./recovery-store.ts";

export function useRecovery<T extends ChatDraft | ReportDraft>(key: string) {
  const snapshot = useSyncExternalStore(subscribeRecovery, () =>
    recoverySnapshot(key),
  );
  useEffect(() => {
    void hydrateRecovery(key);
  }, [key]);
  return {
    value: snapshot.value as T | null,
    error: snapshot.error,
    saving: snapshot.saving,
    ready: snapshot.ready,
    write: (value: T | null) => writeRecovery(key, value),
  };
}

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Tablet as TabletIcon, Check, Undo2 } from "lucide-react";
import { api, type Conversation } from "./api.ts";

export function TabletStatus({
  assistant = false,
  warnings = [],
}: {
  assistant?: boolean;
  warnings?: string[];
}) {
  const [status, setStatus] = useState<{
    connected: boolean;
    model: string;
    label: string;
    transport?: string;
    error?: string;
  }>();
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      setStatus(await api("/tablet/status"));
    } catch (e) {
      setStatus({
        connected: false,
        model: "",
        label: "Galaxy tablet",
        error: (e as Error).message,
      });
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  return (
    <div className="tablet-status" role="status">
      <TabletIcon size={19} />
      <div>
        <strong>
          {status?.connected
            ? `${status.label} · ${status.transport === "On-device" ? "On-device tools connected" : "USB connected"}`
            : busy
              ? "Checking tablet connection…"
              : "Tablet disconnected"}
        </strong>
        <span>
          {status?.connected
            ? assistant
              ? "Reads Outlook on your unlocked tablet, then returns here. Opening mail may mark it read."
              : "Find shared files, check health and review small settings changes."
            : status?.error || "Connect and unlock your tablet."}
        </span>
        {assistant && warnings.length ? (
          <span className="outlook-warning">
            Last Outlook check: {warnings.join(" ")}
          </span>
        ) : null}
      </div>
      <button
        className="icon-button"
        aria-label="Check tablet connection"
        disabled={busy}
        onClick={() => void refresh()}
      >
        <RefreshCw size={17} />
      </button>
    </div>
  );
}
type Action = {
  id: string;
  label: string;
  before: string;
  after: string;
  reason: string;
  status: string;
  result: string;
};
export function TabletActions({
  conversation,
  revision,
  notify,
  onReady,
}: {
  conversation: Conversation | null;
  revision: number;
  notify: (text: string) => void;
  onReady: () => void;
}) {
  const [actions, setActions] = useState<Action[]>([]),
    [pending, setPending] = useState("");
  const running = ["starting", "running", "waiting", "stopping"].includes(
    conversation?.status || "",
  );
  useEffect(() => {
    if (actions.length) onReady();
  }, [actions, onReady]);
  useEffect(() => {
    let cancelled = false;
    setActions([]);
    if (conversation)
      void api<Action[]>(
        `/tablet/actions?conversationId=${encodeURIComponent(conversation.id)}`,
      )
        .then((rows) => {
          if (!cancelled) setActions(rows);
        })
        .catch((e) => {
          if (!cancelled) notify(e.message);
        });
    return () => {
      cancelled = true;
    };
  }, [conversation?.id, conversation?.status, revision, notify]);
  async function decide(id: string, decision: string) {
    if (pending) return;
    setPending(id);
    try {
      const row = await api<Action>(`/tablet/actions/${id}`, "POST", {
        decision,
      });
      setActions((old) => old.map((a) => (a.id === id ? row : a)));
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setPending("");
    }
  }
  if (!actions.length) return null;
  return (
    <section className="tablet-changes" aria-label="Tablet setting changes">
      {actions.map((a) => (
        <article className="tablet-change" key={a.id}>
          <strong>
            <TabletIcon size={16} /> {a.label}
          </strong>
          <p className="setting-values">
            {a.before} <span aria-label="changes to">→</span> {a.after}
          </p>
          <p>{a.reason}</p>
          {a.status === "proposed" ? (
            <>
              <p className="muted">
                {running
                  ? "Review this change when the answer finishes."
                  : "Only this setting on your Galaxy tablet will change. You can undo it afterward."}
              </p>
              <div className="answer-actions">
                <button
                  className="primary compact"
                  disabled={running || !!pending}
                  onClick={() => void decide(a.id, "apply")}
                >
                  Apply change
                </button>
                <button
                  className="secondary compact"
                  disabled={running || !!pending}
                  onClick={() => void decide(a.id, "decline")}
                >
                  Leave as is
                </button>
              </div>
            </>
          ) : (
            <p role="status">
              <Check size={14} /> {a.result || a.status}
            </p>
          )}
          {a.status === "applied" ? (
            <button
              className="secondary compact"
              disabled={running || !!pending}
              onClick={() => void decide(a.id, "undo")}
            >
              <Undo2 size={15} /> Undo change
            </button>
          ) : null}
        </article>
      ))}
    </section>
  );
}

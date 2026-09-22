import { useEffect, useRef, useState } from "react";
import {
  Cloud,
  ArrowUpRight,
  Folder,
  FileText,
  ArrowLeft,
  Check,
  LoaderCircle,
  Plus,
  Trash2,
} from "lucide-react";
import { api, type Account, type Bootstrap, type Project } from "./api.ts";

type Props = {
  target?: { project: Project; conversationId?: string } | null;
  clearTarget?: () => void;
  added?: (project: Project) => Promise<void>;
  data: Bootstrap;
  refresh: () => Promise<void>;
  notify: (text: string) => void;
  openProject: (project: Project) => void;
};
export function Connections({
  data,
  refresh,
  notify,
  openProject,
  target,
  clearTarget,
  added,
}: Props) {
  const [accounts, setAccounts] = useState(data.accounts);
  const [accountErrors, setAccountErrors] = useState<Record<number, string>>(
    {},
  );
  const [connectingSlot, setConnectingSlot] = useState<number | null>(null);
  const [removingSlot, setRemovingSlot] = useState<number | null>(null);
  const importRequest = useRef<{ fingerprint: string; id: string } | null>(
    null,
  );
  const accountRevision = useRef(0);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const browserHeadingRef = useRef<HTMLHeadingElement>(null);
  const [labels, setLabels] = useState<Record<number, string>>({}),
    [slot, setSlot] = useState<number | null>(null);
  const [stack, setStack] = useState<{ id: string; name: string }[]>([]),
    [items, setItems] = useState<any[]>([]),
    [cursor, setCursor] = useState<string | undefined>();
  const [selected, setSelected] = useState<
      { slot: number; itemId: string; name: string; connectionId?: string }[]
    >([]),
    [collection, setCollection] = useState("Meeting documents"),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    setAccounts(data.accounts);
  }, [data.accounts]);
  useEffect(() => {
    let mounted = true;
    const timer = setInterval(() => {
      const revision = accountRevision.current;
      void api<Account[]>("/accounts")
        .then((a) => {
          if (mounted && revision === accountRevision.current) setAccounts(a);
        })
        .catch(() => {});
    }, 2500);
    return () => {
      mounted = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    const connected = new Set(
      accounts.filter((a) => a.status === "connected").map((a) => a.slot),
    );
    if (slot !== null && !connected.has(slot)) setSlot(null);
    setSelected((previous) =>
      previous.filter((item) => connected.has(item.slot)),
    );
  }, [accounts, slot]);
  useEffect(() => {
    if (slot === null) return;
    let current = true;
    setLoading(true);
    setItems([]);
    setCursor(undefined);
    browserHeadingRef.current?.focus({ preventScroll: true });
    browserHeadingRef.current?.scrollIntoView({ block: "start" });
    void api(
      `/accounts/${slot}/files?item=${encodeURIComponent(
        stack.at(-1)?.id || "root",
      )}`,
    )
      .then((page) => {
        if (current) {
          setItems(page.items);
          setCursor(page.nextCursor);
        }
      })
      .catch((e) => {
        if (current) notify(e.message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [slot, stack, notify]);
  async function run(action: () => Promise<void>, onError = notify) {
    setBusy(true);
    try {
      await action();
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function connect(account: Account) {
    setConnectingSlot(account.slot);
    setAccountErrors((errors) => ({ ...errors, [account.slot]: "" }));
    await run(
      async () => {
        if (!data.microsoftConfigured) {
          const latest = await api<Bootstrap>("/bootstrap");
          if (!latest.microsoftConfigured)
            throw new Error(
              "Microsoft sign-in is not ready yet. The person setting up Galaxy Workspace needs to enable it. You can keep using your connected accounts below.",
            );
        }
        await api(`/accounts/${account.slot}/connect`, "POST", {
          label: labels[account.slot] || account.label,
        });
      },
      (message) =>
        setAccountErrors((errors) => ({ ...errors, [account.slot]: message })),
    );
    setConnectingSlot(null);
  }
  async function remove(account: Account) {
    setRemovingSlot(account.slot);
    accountRevision.current++;
    setAccountErrors((errors) => ({ ...errors, [account.slot]: "" }));
    await run(
      async () => {
        await api(`/accounts/${account.slot}/remove`, "POST", {});
        accountRevision.current++;
        setAccounts((current) =>
          current.filter((a) => a.slot !== account.slot),
        );
        setSelected((current) =>
          current.filter((item) => item.slot !== account.slot),
        );
        setLabels((current) => {
          const next = { ...current };
          delete next[account.slot];
          return next;
        });
        if (slot === account.slot) setSlot(null);
        notify(
          `${account.label} removed. Your files and saved conversations are kept.`,
        );
      },
      (message) =>
        setAccountErrors((errors) => ({ ...errors, [account.slot]: message })),
    );
    setRemovingSlot(null);
    requestAnimationFrame(() => addButtonRef.current?.focus());
  }
  return (
    <section className="connections-page">
      {target ? (
        <div className="collection-target">
          <strong>Adding to {target.project.name}</strong>
          <p>
            Browse folders and accounts, select your material, then tap Add to
            workspace.
          </p>
          <button
            className="secondary"
            onClick={() => {
              clearTarget?.();
              openProject(target.project);
            }}
          >
            Back to workspace
          </button>
        </div>
      ) : null}
      <div className="eyebrow">CONNECTED TO YOUR WORLD</div>
      <h1>Your files, together.</h1>
      <p className="page-intro">
        Connect your personal and work OneDrive accounts. Choose the documents
        you want to bring into a conversation. Sign in with your usual Microsoft
        email and password on Microsoft’s page.
      </p>
      {!data.microsoftConfigured ? (
        <div className="setup-card" role="status">
          <Cloud size={24} />
          <div>
            <h3>Microsoft sign-in isn’t ready yet</h3>
            <p>
              The person setting up Galaxy Workspace needs to enable Microsoft
              sign-in once. After that, you’ll only need your normal Microsoft
              login to connect each account.
            </p>
            {accounts.some((a) => a.status === "connected") ? (
              <p>Your connected accounts below are ready to use.</p>
            ) : null}
          </div>
        </div>
      ) : null}
      <div className="connection-controls">
        <p>
          Remove any connection you no longer need. OneDrive files and saved
          conversations are kept.
        </p>
        {accounts.filter((a) => a.source !== "host").length < 3 ? (
          <button
            ref={addButtonRef}
            className="secondary"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                accountRevision.current++;
                const added = await api<{ slot: number }>(
                  "/accounts",
                  "POST",
                  {},
                );
                setAccountErrors((errors) => ({ ...errors, [added.slot]: "" }));
              })
            }
          >
            <Plus size={17} /> Add OneDrive account
          </button>
        ) : null}
      </div>
      <div className="account-grid">
        {[...accounts]
          .sort(
            (a, b) => Number(b.source === "host") - Number(a.source === "host"),
          )
          .map((account) => (
            <article
              className={`account-card ${
                account.status === "connected" ? "is-connected" : ""
              }`}
              key={account.slot}
            >
              <div className="account-top">
                <span className={`cloud-icon cloud-${account.slot}`}>
                  <Cloud size={25} />
                </span>
                <span className={`status-label ${account.status}`}>
                  {account.status === "connected"
                    ? "Connected"
                    : account.status === "connecting"
                      ? "Sign-in pending"
                      : !data.microsoftConfigured
                        ? "Sign-in not ready"
                        : "Not connected"}
                </span>
              </div>
              <label className="account-label">
                {account.source === "host"
                  ? (data.runtime === "tablet" ? "Linked on this tablet" : "Linked from this host")
                  : `Connection ${account.slot}`}
                <input
                  aria-label={`Name for OneDrive ${account.slot}`}
                  value={labels[account.slot] ?? account.label}
                  onChange={(e) =>
                    setLabels({ ...labels, [account.slot]: e.target.value })
                  }
                  maxLength={60}
                  readOnly={account.source === "host"}
                />
              </label>
              <p>{account.username || "Personal or work account"}</p>
              {account.readOnly ? (
                <p>
                  Browse and import for assessment. Edits stay in your local
                  draft.
                </p>
              ) : null}
              {account.status !== "connected" && !data.microsoftConfigured ? (
                <p className="setup-hint" id={`setup-hint-${account.slot}`}>
                  Microsoft sign-in needs to be enabled for this workspace
                  first.
                </p>
              ) : null}
              {account.status === "connecting" && !account.login?.code ? (
                <p role="status">Getting your Microsoft sign-in code…</p>
              ) : null}
              {account.login?.code ? (
                <div className="device-code" aria-live="polite">
                  <span>1. Use this one-time sign-in code</span>
                  <strong>{account.login.code}</strong>
                  <a
                    className="primary"
                    href={account.login.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    2. Sign in at Microsoft <ArrowUpRight size={16} />
                  </a>
                  <p>
                    Enter the code, sign in with your usual account, then return
                    here.
                  </p>
                </div>
              ) : null}
              {accountErrors[account.slot] || account.error ? (
                <p className="inline-error" role="alert">
                  {accountErrors[account.slot] || account.error}
                </p>
              ) : null}
              <div className="account-actions">
                {account.status === "connected" ? (
                  <>
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => {
                        setSlot(account.slot);
                        setStack([]);
                      }}
                    >
                      Browse files
                    </button>
                  </>
                ) : (
                  <button
                    className="secondary"
                    aria-describedby={
                      !data.microsoftConfigured
                        ? `setup-hint-${account.slot}`
                        : undefined
                    }
                    disabled={busy || account.status === "connecting"}
                    onClick={() => void connect(account)}
                  >
                    {connectingSlot === account.slot
                      ? "Starting sign-in…"
                      : account.status === "connecting"
                        ? "Waiting for Microsoft…"
                        : !data.microsoftConfigured
                          ? "Check sign-in availability"
                          : "Sign in with Microsoft"}
                    <ArrowUpRight size={16} />
                  </button>
                )}
                <button
                  className="remove-connection"
                  aria-label={`Remove ${account.label}`}
                  disabled={busy}
                  onClick={() => void remove(account)}
                >
                  <Trash2 size={16} />{" "}
                  {removingSlot === account.slot ? "Removing…" : "Remove"}
                </button>
              </div>
            </article>
          ))}
      </div>
      {slot !== null ? (
        <div className="cloud-browser">
          <div className="section-heading">
            <div>
              <span className="small-label">
                {accounts.find((a) => a.slot === slot)?.label}
              </span>
              <h3 ref={browserHeadingRef} tabIndex={-1}>
                {stack.at(-1)?.name || "Your OneDrive files"}
              </h3>
            </div>
            {stack.length ? (
              <button
                className="secondary"
                onClick={() => setStack((s) => s.slice(0, -1))}
              >
                <ArrowLeft size={16} /> Back
              </button>
            ) : null}
          </div>
          {loading ? (
            <p>
              <LoaderCircle size={18} /> Loading files…
            </p>
          ) : items.length === 0 ? (
            <p>This folder has no files.</p>
          ) : (
            <div className="cloud-files">
              {items.map((item) => {
                const picked = selected.some(
                  (s) => s.slot === slot && s.itemId === item.id,
                );
                return (
                  <div className="cloud-file" key={item.id}>
                    <button
                      aria-label={`${picked ? "Deselect" : "Select"} ${
                        item.name
                      }`}
                      aria-pressed={picked}
                      className={`select-file ${picked ? "selected" : ""}`}
                      onClick={() =>
                        setSelected((s) =>
                          picked
                            ? s.filter(
                                (f) =>
                                  !(f.slot === slot && f.itemId === item.id),
                              )
                            : [
                                ...s,
                                {
                                  slot,
                                  itemId: item.id,
                                  name: item.name,
                                  connectionId: accounts.find(
                                    (a) => a.slot === slot,
                                  )?.connectionId,
                                },
                              ],
                        )
                      }
                    >
                      {picked ? <Check size={16} /> : null}
                    </button>
                    {item.directory ? (
                      <Folder size={19} />
                    ) : (
                      <FileText size={19} />
                    )}
                    <button
                      className="cloud-file-name"
                      onClick={() =>
                        item.directory
                          ? setStack((s) => [
                              ...s,
                              { id: item.id, name: item.name },
                            ])
                          : setSelected((s) =>
                              picked
                                ? s
                                : [
                                    ...s,
                                    {
                                      slot,
                                      itemId: item.id,
                                      name: item.name,
                                      connectionId: accounts.find(
                                        (a) => a.slot === slot,
                                      )?.connectionId,
                                    },
                                  ],
                            )
                      }
                    >
                      {item.name}
                    </button>
                    <span>
                      {item.directory
                        ? "Folder"
                        : `${Math.max(1, Math.round(item.size / 1024))} KB`}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          {cursor ? (
            <button
              className="secondary"
              disabled={loading}
              onClick={async () => {
                setLoading(true);
                try {
                  const page = await api(
                    `/accounts/${slot}/files?cursor=${encodeURIComponent(
                      cursor,
                    )}`,
                  );
                  setItems((i) => [...i, ...page.items]);
                  setCursor(page.nextCursor);
                } catch (e) {
                  notify((e as Error).message);
                } finally {
                  setLoading(false);
                }
              }}
            >
              Load more files
            </button>
          ) : null}
        </div>
      ) : null}
      {selected.length ? (
        <form
          className="import-bar"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const payload = {
                name: collection,
                items: selected.map(({ name: _, ...s }) => s),
                projectId: target?.project.id,
                conversationId: target?.conversationId,
              };
              const fingerprint = JSON.stringify(payload);
              if (importRequest.current?.fingerprint !== fingerprint)
                importRequest.current = {
                  fingerprint,
                  id: crypto.randomUUID(),
                };
              const project = await api<Project>("/collections", "POST", {
                ...payload,
                id: importRequest.current.id,
              });
              setSelected([]);
              if (target && added) await added(project);
              else openProject(project);
            });
          }}
        >
          <div>
            <strong>
              {selected.length} selection{selected.length === 1 ? "" : "s"} from{" "}
              {new Set(selected.map((s) => s.slot)).size} account
              {new Set(selected.map((s) => s.slot)).size === 1 ? "" : "s"}
            </strong>
            <span>
              Selected documents will be copied to your host for assessment.
            </span>
          </div>
          {!target ? (
            <input
              aria-label="Document collection name"
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              required
            />
          ) : null}
          <button className="primary" disabled={busy}>
            {busy
              ? "Importing…"
              : target
                ? "Add to workspace"
                : "Open as a workspace"}
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => setSelected([])}
          >
            Clear
          </button>
        </form>
      ) : null}
      <div className="connection-footnote">
        <Cloud size={19} />
        <p>
          Each connection keeps its own identity. Imported documents retain
          their source account and version. Word and PDF text can be assessed;
          preserving their formatting when saving edits is a later step.
        </p>
      </div>
    </section>
  );
}

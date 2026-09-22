import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { documentLink } from "./document-links.ts";
import { answerForReport } from "./chat-content.ts";
import {
  ArrowLeft,
  Cloud,
  Download,
  FileText,
  Folder,
  PencilLine,
  RefreshCw,
} from "lucide-react";
import { api, type Account, type Conversation } from "./api.ts";

type ReportData = {
  path: string;
  configured: boolean;
  exists: boolean;
  text: string;
  hash: string;
};
type ExportData = {
  id: string;
  filename: string;
  format: string;
  hash: string;
};
export function Report({
  meeting = false,
  conversation,
  accounts,
  revision,
  prepare,
  preview,
  refresh,
  addition,
  consumeAddition,
}: {
  meeting?: boolean;
  conversation: Conversation | null;
  accounts: Account[];
  revision: number;
  prepare: (path?: string) => Promise<void>;
  preview: (path: string) => void;
  refresh: () => Promise<void>;
  addition?: { id: string; conversationId: string; text: string } | null;
  consumeAddition: () => void;
}) {
  const [report, setReport] = useState<ReportData | null>(null),
    [error, setError] = useState("");
  const [editing, setEditing] = useState(false),
    [text, setText] = useState(""),
    [editHash, setEditHash] = useState("");
  const [busy, setBusy] = useState(false),
    [format, setFormat] = useState("docx"),
    [exported, setExported] = useState<ExportData | null>(null);
  const [destination, setDestination] = useState(false),
    [slot, setSlot] = useState(""),
    [identity, setIdentity] = useState("");
  const [stack, setStack] = useState<{ id: string; name: string }[]>([]),
    [folders, setFolders] = useState<any[]>([]),
    [cursor, setCursor] = useState<string>();
  const [loading, setLoading] = useState(false),
    [folderError, setFolderError] = useState("");
  const [filename, setFilename] = useState(""),
    [receipt, setReceipt] = useState(""),
    [submitted, setSubmitted] = useState(false);
  const running = ["starting", "running", "waiting", "stopping"].includes(
    conversation?.status || "",
  );
  const writable = accounts.filter(
    (a) => a.status === "connected" && !a.readOnly,
  );
  const account = writable.find((a) => String(a.slot) === slot);
  const handledAddition = useRef("");
  const currentConversation = useRef(conversation?.id);
  currentConversation.current = conversation?.id;
  useEffect(() => {
    setEditing(false);
    setText("");
    setError("");
    setExported(null);
    setDestination(false);
  }, [conversation?.id]);
  useEffect(() => {
    if (
      !addition ||
      addition.id === handledAddition.current ||
      addition.conversationId !== conversation?.id
    )
      return;
    handledAddition.current = addition.id;
    consumeAddition();
    const section =
      "\n\n## From the conversation\n\n" + answerForReport(addition.text);
    if (editing) {
      setText((old) => old.trimEnd() + section);
      return;
    }
    void run(async () => {
      const id = addition.conversationId;
      const latest = await api<ReportData>(
        `/conversations/${id}/report`,
        "POST",
        {},
      );
      if (currentConversation.current !== id) return;
      setReport(latest);
      setText((latest.text || "# Summary report").trimEnd() + section);
      setEditHash(latest.hash);
      setEditing(true);
      setExported(null);
      await refresh();
    });
  }, [addition?.id]);
  useEffect(() => {
    let cancelled = false;
    if (!conversation) {
      setReport(null);
      return;
    }
    void api<ReportData>(`/conversations/${conversation.id}/report`)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [conversation?.id, conversation?.status, revision]);
  useEffect(() => {
    let cancelled = false;
    setFolders([]);
    setCursor(undefined);
    setFolderError("");
    if (!slot || !destination) return;
    setLoading(true);
    void api(
      `/accounts/${slot}/files?item=${encodeURIComponent(stack.at(-1)?.id || "root")}`,
    )
      .then((page) => {
        if (!cancelled) {
          setFolders(page.items.filter((i: any) => i.directory));
          setCursor(page.nextCursor);
        }
      })
      .catch((e) => {
        if (!cancelled) setFolderError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slot, stack, destination]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="report-panel" aria-label="Report draft">
      <div className="report-heading">
        <div>
          <span className="eyebrow">WORKING DOCUMENT</span>
          <h3>{report?.path.split("/").at(-1) || "Summary report"}</h3>
        </div>
        <button
          className="icon-button"
          aria-label="Refresh report"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              if (conversation)
                setReport(
                  await api(`/conversations/${conversation.id}/report`),
                );
            })
          }
        >
          <RefreshCw size={17} />
        </button>
      </div>
      {!report?.exists && !editing ? (
        <div className="report-empty">
          <FileText size={30} />
          <h3>Turn the material into a report.</h3>
          <p>
            Discuss the sources first, or start with a draft. Refine it through
            the conversation and see the saved document here.
          </p>
          <button
            className="primary"
            disabled={busy || running}
            onClick={() => void run(prepare)}
          >
            <PencilLine size={16} />{" "}
            {report?.configured ? "Prepare drafting request" : "Draft a report"}
          </button>
          <p>Review the request in the chat box, then tap Send.</p>
        </div>
      ) : (
        <>
          <div className="report-tools">
            <span>
              {running
                ? "Assistant is working…"
                : editing
                  ? "Review your text, then save"
                  : meeting
                    ? "Saved in this meeting’s workspace folder"
                    : "Saved in this conversation’s draft"}
            </span>
            <button
              className="secondary compact"
              disabled={busy || running}
              onClick={() => {
                if (editing) {
                  setEditing(false);
                  return;
                }
                void run(async () => {
                  if (!report?.configured || conversation?.mode !== "draft")
                    await prepare(report!.path);
                  setText(report!.text);
                  setEditHash(report!.hash);
                  setEditing(true);
                });
              }}
            >
              {editing ? "Cancel editing" : "Edit text"}
            </button>
          </div>
          {editing ? (
            <div className="report-editor">
              <label>
                Edit report (Markdown)
                <textarea
                  aria-label="Report text"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </label>
              <button
                className="primary"
                disabled={busy || running}
                onClick={() =>
                  void run(async () => {
                    const r = await api<ReportData>(
                      `/conversations/${conversation!.id}/report`,
                      "POST",
                      { text, hash: editHash },
                    );
                    setReport(r);
                    setEditing(false);
                    setExported(null);
                    await refresh();
                  })
                }
              >
                {meeting ? "Save brief" : "Save draft text"}
              </button>
            </div>
          ) : (
            <div className="report-document markdown">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="table-scroll">
                      <table>{children}</table>
                    </div>
                  ),
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      onClick={(e) => {
                        if (href && !/^https?:\/\//.test(href)) {
                          e.preventDefault();
                          const path = documentLink(report!.path, href);
                          if (path !== null) preview(path);
                        }
                      }}
                      target={
                        /^https?:\/\//.test(href || "") ? "_blank" : undefined
                      }
                      rel="noreferrer"
                    >
                      {children}
                    </a>
                  ),
                  img: ({ alt }) => <span>{alt || "Image omitted"}</span>,
                }}
              >
                {report?.text || ""}
              </ReactMarkdown>
            </div>
          )}
          <div className="export-controls">
            <h4>Export a copy</h4>
            <p>Save a snapshot of the report. Keep refining the draft here.</p>
            <div className="export-format">
              <label>
                Format
                <select
                  aria-label="Export format"
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                >
                  <option value="docx">Word (.docx)</option>
                  <option value="pdf">PDF (.pdf)</option>
                  <option value="md">Markdown (.md)</option>
                </select>
              </label>
              <button
                className="primary"
                disabled={busy || running || editing}
                onClick={() =>
                  void run(async () => {
                    const r = await api<ExportData>(
                      `/conversations/${conversation!.id}/export`,
                      "POST",
                      { format, hash: report!.hash },
                    );
                    setExported(r);
                    setFilename(r.filename);
                    setReceipt("");
                    setSubmitted(false);
                    setDestination(false);
                  })
                }
              >
                {busy ? "Working…" : "Prepare export"}
              </button>
            </div>
            {exported ? (
              <div className="export-ready">
                <strong>{exported.filename}</strong>
                {exported.hash !== report?.hash ? (
                  <p>
                    The draft has changed. This copy contains the earlier
                    version; prepare a new export for the latest text.
                  </p>
                ) : null}
                <a
                  className="secondary"
                  href={`/api/exports/${exported.id}/download`}
                  download={exported.filename}
                >
                  <Download size={17} /> Download to this device
                </a>
                <button
                  className="secondary"
                  disabled={busy || submitted}
                  onClick={() => setDestination(!destination)}
                >
                  <Cloud size={17} /> Save new file to OneDrive
                </button>
              </div>
            ) : null}
            {destination && exported ? (
              <div className="cloud-destination">
                <label>
                  OneDrive account
                  <select
                    aria-label="Export OneDrive account"
                    disabled={busy || submitted}
                    value={slot}
                    onChange={(e) => {
                      setSlot(e.target.value);
                      setIdentity(
                        writable.find((a) => String(a.slot) === e.target.value)
                          ?.connectionId || "",
                      );
                      setStack([]);
                    }}
                  >
                    <option value="">Choose an account</option>
                    {writable.map((a) => (
                      <option key={a.slot} value={a.slot}>
                        {a.label} · {a.username}
                      </option>
                    ))}
                  </select>
                </label>
                {!writable.length ? (
                  <p>
                    Connect an account with upload access in Connections. The
                    linked host account supports importing only.
                  </p>
                ) : null}
                {slot ? (
                  <>
                    <div className="folder-heading">
                      {stack.length ? (
                        <button
                          className="icon-button"
                          aria-label="Export parent folder"
                          disabled={busy || submitted}
                          onClick={() => setStack((s) => s.slice(0, -1))}
                        >
                          <ArrowLeft size={17} />
                        </button>
                      ) : (
                        <Folder size={17} />
                      )}
                      <strong>
                        {stack.map((s) => s.name).join(" / ") ||
                          "OneDrive root"}
                      </strong>
                    </div>
                    {loading ? (
                      <p>Loading folders…</p>
                    ) : (
                      folders.map((f) => (
                        <button
                          className="destination-folder"
                          key={f.id}
                          disabled={busy || submitted}
                          onClick={() =>
                            setStack((s) => [...s, { id: f.id, name: f.name }])
                          }
                        >
                          <Folder size={17} />
                          {f.name}
                        </button>
                      ))
                    )}
                    {cursor ? (
                      <button
                        className="secondary"
                        disabled={busy || loading}
                        onClick={() =>
                          void run(async () => {
                            const page = await api(
                              `/accounts/${slot}/files?cursor=${encodeURIComponent(cursor)}`,
                            );
                            setFolders((f) => [
                              ...f,
                              ...page.items.filter((i: any) => i.directory),
                            ]);
                            setCursor(page.nextCursor);
                          })
                        }
                      >
                        More folders
                      </button>
                    ) : null}
                    {folderError ? (
                      <p role="alert" className="inline-error">
                        {folderError}
                      </p>
                    ) : null}
                    <label>
                      New filename
                      <input
                        value={filename}
                        maxLength={180}
                        disabled={busy || submitted}
                        onChange={(e) => setFilename(e.target.value)}
                      />
                    </label>
                    <p>
                      Destination:{" "}
                      <strong>
                        {account?.username} /{" "}
                        {stack.map((s) => s.name).join(" / ") ||
                          "OneDrive root"}{" "}
                        / {filename}
                      </strong>
                      . An existing file with that name will not be replaced.
                    </p>
                    <button
                      className="primary"
                      disabled={
                        busy ||
                        submitted ||
                        loading ||
                        !!folderError ||
                        !account ||
                        identity !== account.connectionId
                      }
                      onClick={() =>
                        void run(async () => {
                          setSubmitted(true);
                          const result = await api(
                            `/exports/${exported.id}/onedrive`,
                            "POST",
                            {
                              slot: Number(slot),
                              connectionId: identity,
                              parentId: stack.at(-1)?.id || "root",
                              name: filename,
                            },
                          );
                          setReceipt(result.webUrl);
                          setDestination(false);
                        })
                      }
                    >
                      Save new file here
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
            {receipt ? (
              <p className="export-receipt" role="status">
                Saved to OneDrive.{" "}
                <a href={receipt} target="_blank" rel="noreferrer">
                  Open exported report
                </a>
              </p>
            ) : null}
          </div>
        </>
      )}
      {error ? (
        <p role="alert" className="inline-error">
          {error}
        </p>
      ) : null}
    </section>
  );
}

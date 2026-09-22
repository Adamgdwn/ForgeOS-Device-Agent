import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Sparkles,
  PanelsTopLeft,
  Cloud,
  Plus,
  MessageSquare,
  ChevronDown,
  Folder,
  FileText,
  Monitor,
  ArrowUpRight,
  X,
  ArrowLeft,
  Menu,
  PanelRight,
  PencilLine,
  ShieldCheck,
  LogOut,
  RefreshCw,
  Check,
  Tablet as TabletIcon,
} from "lucide-react";
import {
  api,
  type Activity,
  type Bootstrap,
  type Conversation,
  type FileEntry,
  type Project,
} from "./api.ts";
import { Chat } from "./Chat.tsx";
import { Connections } from "./Connections.tsx";
import { Materials } from "./Materials.tsx";
import { Report } from "./Report.tsx";
import { TabletStatus } from "./Tablet.tsx";
import { outlookWarnings } from "./outlook-warnings.ts";

function Modal({
  children,
  title,
  close,
}: {
  children: ReactNode;
  title: string;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button
          aria-label="Close preview"
          className="icon-button"
          onClick={close}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
function Pair({ done }: { done: () => void }) {
  const [code, setCode] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="pair-page">
      <div className="pair-brand">
        <span className="brand-mark">
          <Sparkles size={23} />
        </span>
        Galaxy<span>WORKSPACE</span>
      </div>
      <div className="pair-card">
        <div className="eyebrow">YOUR WORKSTATION, WITH YOU</div>
        <h1>
          Make room
          <br />
          for a good idea.
        </h1>
        <p>
          Pair this browser to explore your files, continue a conversation, and
          review changes from wherever you work.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              await api("/session", "POST", { code });
              setCode("");
              done();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Workstation pairing code
            <input
              autoFocus
              type="password"
              autoComplete="off"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Enter your pairing code"
              required
            />
          </label>
          {error ? (
            <p role="alert" className="inline-error">
              {error}
            </p>
          ) : null}
          <button className="primary" disabled={busy}>
            {busy ? "Connecting…" : "Open my workspace"}
            <ArrowUpRight size={18} />
          </button>
        </form>
        <details>
          <summary>Where do I find my code?</summary>
          <p>
            On your workstation, open this project folder in a terminal and run{" "}
            <code>npm run pair</code>. Enter the code here. Your Microsoft
            account sign-ins are added separately inside the workspace.
          </p>
        </details>
        <div className="pair-security">
          <ShieldCheck size={16} /> A private connection to your host
        </div>
      </div>
      <div className="pair-orbit" aria-hidden="true">
        <span>✦</span>
      </div>
    </main>
  );
}
export function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null),
    [data, setData] = useState<Bootstrap | null>(null);
  const [page, setPage] = useState<"workspace" | "connections">("workspace"),
    [projectId, setProjectId] = useState(""),
    [conversationId, setConversationId] = useState(
      () =>
        new URLSearchParams(location.hash.slice(1)).get("conversation") || "",
    );
  const [events, setEvents] = useState<Activity[]>([]),
    [connected, setConnected] = useState(true),
    [error, setError] = useState("");
  const [navOpen, setNavOpen] = useState(false),
    [inspectorOpen, setInspectorOpen] = useState(false),
    [tab, setTab] = useState<"files" | "review" | "report">("files");
  const [folder, setFolder] = useState(""),
    [files, setFiles] = useState<FileEntry[]>([]),
    [filesLoading, setFilesLoading] = useState(false),
    [attachments, setAttachments] = useState<string[]>([]);
  const [preview, setPreview] = useState<{
      path: string;
      text: string;
      extracted: boolean;
      truncated: boolean;
      source?: { originalName: string; webUrl: string; label: string };
    } | null>(null),
    [review, setReview] = useState<any[]>([]),
    [reviewBusy, setReviewBusy] = useState(false),
    [draftBusy, setDraftBusy] = useState(false);
  const [materials, setMaterials] = useState<"new" | "current" | null>(null),
    [materialTarget, setMaterialTarget] = useState<{
      project: Project;
      conversationId?: string;
    } | null>(null),
    [revision, setRevision] = useState(0),
    [chatRequest, setChatRequest] = useState<{
      id: string;
      text: string;
    } | null>(null);
  const [reportAddition, setReportAddition] = useState<{
    id: string;
    conversationId: string;
    text: string;
  } | null>(null);
  const conversation =
    data?.conversations.find((c) => c.id === conversationId) || null;
  const project =
    data?.projects.find((p) => p.id === projectId) || data?.projects[0];
  const system = project?.kind === "system";
  const assistant =
    project?.kind === "assistant" || project?.kind === "meeting";
  const notify = useCallback((message: string) => setError(message), []);
  const refresh = useCallback(async () => {
    const next = await api<Bootstrap>("/bootstrap");
    setData(next);
  }, []);
  useEffect(() => {
    const unpair = () => {
      setAuthenticated(false);
      setData(null);
    };
    window.addEventListener("galaxy-unpaired", unpair);
    return () => window.removeEventListener("galaxy-unpaired", unpair);
  }, []);
  useEffect(() => {
    void api<{ authenticated: boolean }>("/session")
      .then((s) => setAuthenticated(s.authenticated))
      .catch((e) => {
        setError(e.message);
        setAuthenticated(false);
      });
  }, []);
  useEffect(() => {
    if (authenticated) void refresh().catch((e) => setError(e.message));
  }, [authenticated, refresh]);
  useEffect(() => {
    history.replaceState(
      null,
      "",
      conversationId
        ? `#conversation=${encodeURIComponent(conversationId)}`
        : location.pathname,
    );
  }, [conversationId]);
  useEffect(() => {
    if (conversation && conversation.projectId !== projectId)
      setProjectId(conversation.projectId);
  }, [conversation?.id, conversation?.projectId]);
  useEffect(() => {
    if (data && !projectId)
      setProjectId(conversation?.projectId || data.projects[0]?.id || "");
  }, [data, projectId, conversation?.projectId]);
  useEffect(() => {
    if (system || !conversation || conversation.projectId !== project?.id)
      return;
    let cancelled = false;
    void api<{ configured: boolean }>(
      `/conversations/${conversation.id}/report`,
    )
      .then((r) => {
        if (!cancelled && r.configured) setTab("report");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [conversation?.id, project?.id, system]);
  useEffect(() => {
    let disposed = false;
    const online = () => {
      if (!disposed) {
        setConnected(true);
        if (authenticated) void refresh().catch(() => setConnected(false));
      }
    };
    const offline = () => setConnected(false);
    window.addEventListener("online", online);
    window.addEventListener("offline", offline);
    return () => {
      disposed = true;
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offline);
    };
  }, [authenticated, refresh]);
  useEffect(() => {
    setEvents([]);
    if (!conversationId) {
      setConnected(navigator.onLine);
      return;
    }
    let cancelled = false,
      stream: EventSource | null = null;
    void api<{ events: Activity[] }>(`/conversations/${conversationId}`)
      .then((result) => {
        if (cancelled) return;
        setEvents(result.events);
        stream = new EventSource(
          `/api/conversations/${conversationId}/events?after=${
            result.events.at(-1)?.seq || 0
          }`,
        );
        stream.onopen = () => setConnected(true);
        stream.onerror = () => setConnected(false);
        stream.onmessage = (message) => {
          const event: Activity = JSON.parse(message.data);
          setEvents((previous) =>
            previous.some((e) => e.seq === event.seq)
              ? previous
              : [...previous, event],
          );
          if (
            [
              "status",
              "notice",
              "saved",
              "question",
              "question-resolved",
              "tablet-action",
            ].includes(event.type)
          )
            void refresh().catch(() => {});
        };
      })
      .catch((e) => {
        if (!cancelled) notify(e.message);
      });
    return () => {
      cancelled = true;
      stream?.close();
    };
  }, [conversationId, refresh, notify]);
  useEffect(() => {
    setFolder("");
    setAttachments([]);
    setTab("files");
  }, [projectId]);
  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    setFilesLoading(true);
    void api<FileEntry[]>(
      `/${
        conversationId
          ? `conversations/${conversationId}`
          : `projects/${project.id}`
      }/files?path=${encodeURIComponent(folder)}`,
    )
      .then((entries) => {
        if (!cancelled) setFiles(entries);
      })
      .catch((e) => {
        if (!cancelled) notify(e.message);
      })
      .finally(() => {
        if (!cancelled) setFilesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    project?.id,
    folder,
    conversationId,
    conversation?.mode,
    conversation?.status,
    notify,
    revision,
    events.filter((e) => ["saved", "notice"].includes(e.type)).length,
  ]);
  useEffect(() => {
    if (tab !== "review" || !conversationId) return;
    let cancelled = false;
    setReviewBusy(true);
    void api<any[]>(`/conversations/${conversationId}/changes`)
      .then((result) => {
        if (!cancelled) setReview(result);
      })
      .catch((e) => {
        if (!cancelled) notify(e.message);
      })
      .finally(() => {
        if (!cancelled) setReviewBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, conversationId, conversation?.status, conversation?.mode, notify]);
  const openPreview = useCallback(
    async (path: string) => {
      if (!project) return;
      for (const root of [conversation?.workspace, project.path])
        if (root && path.startsWith(root + "/"))
          path = path.slice(root.length + 1);
      path = path.split("#")[0];
      try {
        setPreview(
          await api(
            `/${
              conversationId
                ? `conversations/${conversationId}`
                : `projects/${project.id}`
            }/preview?path=${encodeURIComponent(path)}`,
          ),
        );
      } catch (e) {
        notify((e as Error).message);
      }
    },
    [project, conversationId, conversation?.workspace, notify],
  );
  async function newConversation() {
    if (!project) throw new Error("Choose a workspace first.");
    const created = await api<Conversation>("/conversations", "POST", {
      projectId: project.id,
    });
    setConversationId(created.id);
    setPage("workspace");
    await refresh();
    return created;
  }
  function chooseProject(p: Project) {
    setProjectId(p.id);
    setConversationId(
      data?.conversations.find((c) => c.projectId === p.id)?.id || "",
    );
    setPage("workspace");
    setNavOpen(false);
  }
  async function startDraft() {
    setDraftBusy(true);
    try {
      const c = conversation || (await newConversation());
      await api(`/conversations/${c.id}/draft`, "POST", {});
      await refresh();
      setTab("review");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setDraftBusy(false);
    }
  }
  async function prepareReport(path?: string) {
    const c = conversation || (await newConversation());
    const report = await api<{ path: string; exists: boolean }>(
      `/conversations/${c.id}/report`,
      "POST",
      { path },
    );
    await refresh();
    setRevision((r) => r + 1);
    setTab("report");
    setInspectorOpen(true);
    if (!path)
      setChatRequest({
        id: crypto.randomUUID(),
        text: `Read the source documents, email extracts, attachments and SOURCE_INDEX.md files in this workspace. ${report.exists ? "Refine" : "Create"} the report at ${report.path}, using our discussion so far. Include an executive summary, supported findings, conflicts or gaps, and next actions with owners and dates where the sources support them. Cite source files with relative links, distinguish assumptions from facts, and flag unreadable or truncated sources. Preserve the source material. If a critical detail is missing, ask me first.`,
      });
  }
  async function materialsDone(p: Project) {
    await refresh();
    setMaterials(null);
    setRevision((r) => r + 1);
    setFolder("");
    if (p.id !== project?.id) chooseProject(p);
    setPage("workspace");
  }
  if (authenticated === null)
    return (
      <main className="loading-page">
        <Sparkles size={30} />
        <p>Opening Galaxy Workspace…</p>
      </main>
    );
  if (!authenticated) return <Pair done={() => setAuthenticated(true)} />;
  if (!data || !project)
    return (
      <main className="loading-page">
        <Sparkles size={30} />
        <p>{error || "Connecting to your workstation…"}</p>
        {error ? (
          <button
            className="secondary"
            onClick={() => void refresh().catch((e) => notify(e.message))}
          >
            Retry connection
          </button>
        ) : null}
      </main>
    );
  const busy = ["starting", "running", "waiting", "stopping"].includes(
    conversation?.status || "",
  );
  return (
    <div
      className={`app-shell ${navOpen ? "nav-open" : ""} ${
        inspectorOpen ? "inspector-open" : ""
      }`}
    >
      {navOpen ? (
        <button
          className="nav-backdrop"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      ) : null}
      <aside className="sidebar">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            setPage("workspace");
          }}
        >
          <span className="brand-mark">
            <Sparkles size={21} />
          </span>
          <div>
            Galaxy<span>WORKSPACE</span>
          </div>
        </a>
        <span className="sidebar-caption">A LITTLE MORE POSSIBLE.</span>
        <nav aria-label="Main navigation">
          <button
            className={page === "workspace" ? "nav-item active" : "nav-item"}
            onClick={() => {
              setPage("workspace");
              setNavOpen(false);
            }}
          >
            <PanelsTopLeft size={18} /> Workspace
            <span className="nav-dot" />
          </button>
          <button
            className={page === "connections" ? "nav-item active" : "nav-item"}
            onClick={() => {
              setPage("connections");
              setNavOpen(false);
            }}
          >
            <Cloud size={18} /> Connections
            <span className="nav-count">
              {data.accounts.filter((a) => a.status === "connected").length}/
              {data.accounts.length}
            </span>
          </button>
        </nav>
        <div className="sidebar-section">
          <span>YOUR WORKSPACES</span>
          <button
            aria-label="New workspace"
            onClick={() => {
              setMaterials("new");
              setNavOpen(false);
            }}
          >
            <Plus size={17} />
          </button>
        </div>
        <div className="project-list">
          {data.projects.map((p) => (
            <button
              key={p.id}
              className={`project-item ${
                project.id === p.id && page === "workspace" ? "selected" : ""
              }`}
              onClick={() => chooseProject(p)}
            >
              {p.kind === "assistant" ? (
                <Sparkles size={16} />
              ) : p.kind === "meeting" ? (
                <MessageSquare size={16} />
              ) : p.kind === "system" ? (
                <TabletIcon size={16} />
              ) : p.kind === "onedrive" ? (
                <Cloud size={16} />
              ) : (
                <Folder size={16} />
              )}
              <span>{p.name}</span>
            </button>
          ))}
        </div>
        <div className="sidebar-section">
          <span>CONVERSATIONS</span>
          <button
            aria-label="New conversation"
            onClick={() => {
              setConversationId("");
              setPage("workspace");
              setNavOpen(false);
            }}
          >
            <Plus size={17} />
          </button>
        </div>
        <div className="history-list">
          {data.conversations.length ? (
            data.conversations.slice(0, 30).map((c) => (
              <button
                key={c.id}
                className={
                  conversationId === c.id
                    ? "history-item selected"
                    : "history-item"
                }
                onClick={() => {
                  setProjectId(c.projectId);
                  setConversationId(c.id);
                  setPage("workspace");
                  setNavOpen(false);
                }}
              >
                <MessageSquare size={15} />
                <span>{c.title}</span>
                {["running", "starting", "waiting"].includes(c.status) ? (
                  <span className="pulse-dot" />
                ) : null}
              </button>
            ))
          ) : (
            <p>
              Your conversations will stay here,
              <br />
              ready when you return.
            </p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="host-card">
            <Monitor size={17} />
            <div>
              <strong>
                {data.runtime === "tablet"
                  ? "This Galaxy tablet"
                  : "Linux workstation"}
              </strong>
              <span>
                <i
                  className={data.host.available ? "online-dot" : "offline-dot"}
                />
                {data.host.available ? "Codex ready" : "Codex unavailable"}
              </span>
            </div>
          </div>
          <div className="profile">
            <span className="avatar">AG</span>
            <div>
              <strong>Your workspace</strong>
              <span>Private · This browser is paired</span>
            </div>
            <button
              className="logout"
              aria-label="Unpair this browser"
              onClick={async () => {
                await api("/session", "DELETE");
                setAuthenticated(false);
                setData(null);
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main-workspace">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setNavOpen(!navOpen)}
            >
              <Menu size={21} />
            </button>
            <span>My workspace</span>
            <span className="breadcrumb-slash">/</span>
            <strong>
              {page === "connections" ? "Connections" : project.name}
            </strong>
          </div>
          <div className="topbar-actions">
            <span
              className={`connection-pill ${
                connected && data.host.compatible ? "" : "disconnected"
              }`}
            >
              <span className="small-dot" />
              {!connected
                ? "Reconnecting"
                : data.host.compatible
                  ? data.runtime === "tablet"
                    ? "Running on this tablet"
                    : "Connected to host"
                  : "Codex update needed"}
            </span>
            <button
              className="icon-button inspector-toggle"
              aria-label="Toggle files panel"
              onClick={() => setInspectorOpen(!inspectorOpen)}
            >
              <PanelRight size={19} />
            </button>
          </div>
        </header>
        {error ? (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="Dismiss message"
              onClick={() => setError("")}
            >
              <X size={17} />
            </button>
          </div>
        ) : null}
        {page === "connections" ? (
          <Connections
            data={data}
            refresh={refresh}
            notify={notify}
            openProject={chooseProject}
            target={materialTarget}
            clearTarget={() => setMaterialTarget(null)}
            added={async (p) => {
              await materialsDone(p);
              setMaterialTarget(null);
            }}
          />
        ) : (
          <>
            <div className="workspace-toolbar">
              <div>
                <span className="workspace-symbol">
                  <Folder size={19} />
                </span>
                <div>
                  <strong>
                    {conversation?.title || "A fresh perspective"}
                  </strong>
                  <span>
                    {conversation
                      ? "Saved conversation"
                      : "Start with a question. Take it from there."}
                  </span>
                </div>
              </div>
              <div className="mode-actions">
                <span className="mode-pill">
                  {conversation?.mode === "draft" ? (
                    <PencilLine size={14} />
                  ) : (
                    <Sparkles size={14} />
                  )}{" "}
                  {system
                    ? "This tablet"
                    : assistant
                      ? "Meeting preparation"
                      : conversation?.mode === "draft"
                        ? "Draft changes"
                        : "Explore"}
                </span>
                {!system && !assistant && conversation?.mode !== "draft" ? (
                  <button
                    className="secondary compact"
                    disabled={busy || draftBusy}
                    onClick={() => void startDraft()}
                  >
                    <PencilLine size={15} />
                    {draftBusy ? "Preparing…" : "Start a draft"}
                  </button>
                ) : null}
              </div>
            </div>
            {system ? (
              <TabletStatus />
            ) : assistant ? (
              <TabletStatus assistant warnings={outlookWarnings(events)} />
            ) : (
              <div className="workflow-bar" aria-label="Workspace actions">
                <button
                  className="secondary compact"
                  disabled={busy || draftBusy}
                  onClick={() => setMaterials("current")}
                >
                  <Plus size={16} /> Add material
                </button>
                <button
                  className="secondary compact"
                  disabled={busy || draftBusy}
                  onClick={() => {
                    setDraftBusy(true);
                    void prepareReport()
                      .catch((e) => notify(e.message))
                      .finally(() => setDraftBusy(false));
                  }}
                >
                  <FileText size={16} /> Draft report
                </button>
              </div>
            )}
            <div
              className={`workspace-body ${tab === "report" ? "with-report" : ""}`}
            >
              <Chat
                project={project}
                conversation={conversation}
                events={events}
                connected={connected}
                onNew={newConversation}
                refresh={refresh}
                onPreview={(path) => void openPreview(path)}
                attachments={attachments}
                setAttachments={setAttachments}
                notify={notify}
                request={chatRequest}
                onAddToReport={(text) => {
                  if (!conversation) return;
                  setReportAddition({
                    id: crypto.randomUUID(),
                    conversationId: conversation.id,
                    text,
                  });
                  setTab("report");
                  setInspectorOpen(true);
                }}
              />
              <aside
                className={`inspector ${tab === "report" ? "report-inspector" : ""}`}
              >
                <div className="inspector-tabs">
                  <button
                    className={tab === "files" ? "active" : ""}
                    onClick={() => setTab("files")}
                  >
                    {system ? "Tablet files" : "Files"}
                    <span>{files.length}</span>
                  </button>
                  <button
                    hidden={system || assistant}
                    className={tab === "review" ? "active" : ""}
                    onClick={() => setTab("review")}
                  >
                    Review
                  </button>
                  <button
                    hidden={system}
                    className={tab === "report" ? "active" : ""}
                    onClick={() => setTab("report")}
                  >
                    {assistant ? "Meeting brief" : "Report"}
                  </button>
                  <button
                    className="icon-button inspector-close"
                    aria-label="Close files panel"
                    onClick={() => setInspectorOpen(false)}
                  >
                    <X size={17} />
                  </button>
                </div>
                {!system && (
                  <div className="report-container" hidden={tab !== "report"}>
                    <Report
                      meeting={assistant}
                      addition={reportAddition}
                      consumeAddition={() => setReportAddition(null)}
                      key={conversationId || project.id}
                      conversation={conversation}
                      accounts={data.accounts}
                      revision={
                        revision +
                        events.filter((e) =>
                          ["saved", "notice"].includes(e.type),
                        ).length
                      }
                      prepare={prepareReport}
                      preview={(path) => void openPreview(path)}
                      refresh={refresh}
                    />
                  </div>
                )}
                {tab === "report" ? null : tab === "files" ? (
                  <>
                    <div className="file-location">
                      <Folder size={15} />
                      <strong>{folder || project.name}</strong>
                      {folder ? (
                        <button
                          className="icon-button"
                          aria-label="Parent folder"
                          onClick={() =>
                            setFolder(folder.split("/").slice(0, -1).join("/"))
                          }
                        >
                          <ArrowLeft size={15} />
                        </button>
                      ) : (
                        <ChevronDown size={14} />
                      )}
                    </div>
                    <div className="files-list">
                      {filesLoading ? (
                        <p className="muted">Loading files…</p>
                      ) : files.length ? (
                        files.map((file) => (
                          <button
                            className="file-row"
                            key={file.path}
                            onClick={() =>
                              file.directory
                                ? setFolder(file.path)
                                : void openPreview(file.path)
                            }
                          >
                            <span
                              className={`file-icon ${
                                file.directory ? "folder-icon" : ""
                              }`}
                            >
                              {file.directory ? (
                                <Folder size={18} />
                              ) : (
                                <FileText size={18} />
                              )}
                            </span>
                            <span>
                              <strong>{file.name}</strong>
                              <small>
                                {file.directory
                                  ? "Folder"
                                  : `${Math.max(
                                      1,
                                      Math.round(file.size / 1024),
                                    )} KB · ${file.name
                                      .split(".")
                                      .at(-1)
                                      ?.toUpperCase()}`}
                              </small>
                            </span>
                          </button>
                        ))
                      ) : (
                        <p className="muted">
                          {project.kind === "assistant"
                            ? "Sources will appear as Galaxy reads for this conversation."
                            : "This folder is empty."}
                        </p>
                      )}
                    </div>
                    <div className="file-hint">
                      <Sparkles size={17} />
                      <strong>
                        {system
                          ? "Tablet shared storage"
                          : project.kind === "assistant"
                            ? "Start talking. Galaxy will organize."
                            : "A folder is a starting point."}
                      </strong>
                      <p>
                        {system
                          ? "Browse shared files, or ask Codex to find a filename. Open a document to read it or add it to your question."
                          : project.kind === "assistant"
                            ? "Ask for a meeting brief. Galaxy saves it with its sources in a named workspace, ready to reopen and refine."
                            : "Galaxy can explore these files together. Open a document to read it or add it to your question."}
                      </p>
                    </div>
                    <button
                      hidden={system || project.kind === "assistant"}
                      className="connect-shortcut"
                      onClick={() => setMaterials("current")}
                    >
                      <Cloud size={19} />
                      <span>Add documents and emails</span>
                      <ArrowUpRight size={16} />
                    </button>
                  </>
                ) : (
                  <div className="review-panel">
                    <div className="review-heading">
                      <h3>Changes to review</h3>
                      <button
                        className="icon-button"
                        aria-label="Refresh changes"
                        onClick={async () => {
                          if (conversation) {
                            try {
                              setReview(
                                await api(
                                  `/conversations/${conversation.id}/changes`,
                                ),
                              );
                            } catch (e) {
                              notify((e as Error).message);
                            }
                          }
                        }}
                      >
                        <RefreshCw size={16} />
                      </button>
                    </div>
                    {reviewBusy ? (
                      <p>Reading draft changes…</p>
                    ) : review.length ? (
                      review.map((change) => (
                        <details className="change-card" key={change.path} open>
                          <summary>
                            <FileText size={15} />
                            {change.path}
                            <span>{change.kind}</span>
                          </summary>
                          {change.conflict ? (
                            <p className="inline-error">
                              The original has changed since this draft started.
                            </p>
                          ) : null}
                          <pre className="diff-preview">{change.diff}</pre>
                          <button
                            className="primary"
                            disabled={
                              busy ||
                              !change.applicable ||
                              change.conflict ||
                              change.readOnly
                            }
                            onClick={async () => {
                              try {
                                await api(
                                  `/conversations/${conversationId}/${
                                    change.cloudSource ? "save" : "apply"
                                  }`,
                                  "POST",
                                  { path: change.path },
                                );
                                setReview(
                                  await api(
                                    `/conversations/${conversationId}/changes`,
                                  ),
                                );
                                await refresh();
                              } catch (e) {
                                notify((e as Error).message);
                              }
                            }}
                          >
                            <Check size={16} />
                            {change.readOnly
                              ? "Kept in local draft"
                              : change.cloudSource
                                ? "Save to OneDrive"
                                : "Save to workspace"}
                          </button>
                        </details>
                      ))
                    ) : (
                      <div className="review-empty">
                        <PencilLine size={25} />
                        <strong>
                          {conversation?.mode === "draft"
                            ? "Your draft is ready."
                            : "Room for improvement."}
                        </strong>
                        <p>
                          {conversation?.mode === "draft"
                            ? "Ask for a change in the conversation. You’ll see the result here before saving it."
                            : "Start a draft when you want to turn the conversation into a change. Your originals stay in place while you review."}
                        </p>
                      </div>
                    )}
                  </div>
                )}
                <div className="inspector-footer">
                  <ShieldCheck size={14} />
                  {system
                    ? "Tablet shared storage · originals stay in place"
                    : assistant
                      ? "Meeting files · saved in this workspace"
                      : conversation?.mode === "draft"
                        ? "Editing a separate draft"
                        : "Exploring your original files"}
                </div>
              </aside>
            </div>
          </>
        )}
      </main>
      {materials ? (
        <Modal
          title={materials === "new" ? "New workspace" : "Add material"}
          close={() => setMaterials(null)}
        >
          <Materials
            project={materials === "current" ? project : undefined}
            conversationId={
              materials === "current" ? conversation?.id : undefined
            }
            close={() => setMaterials(null)}
            done={materialsDone}
            cloud={async (p) => {
              await refresh();
              setMaterialTarget({
                project: p,
                conversationId:
                  materials === "current" ? conversation?.id : undefined,
              });
              setMaterials(null);
              setPage("connections");
            }}
          />
        </Modal>
      ) : null}
      {preview ? (
        <Modal
          title={preview.path.split("/").at(-1) || "File preview"}
          close={() => setPreview(null)}
        >
          <div className="preview-meta">
            {preview.extracted
              ? "Extracted text · original formatting is not shown"
              : "Document preview"}
            {preview.truncated ? " · Preview truncated" : ""}
          </div>
          {preview.source ? (
            <div className="source-reference">
              <Cloud size={15} />
              <span>
                {preview.source.label} · {preview.source.originalName}
              </span>
              {preview.source.webUrl.startsWith("https://") ? (
                <a
                  href={preview.source.webUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open original <ArrowUpRight size={14} />
                </a>
              ) : null}
            </div>
          ) : null}
          <pre className="document-preview">{preview.text}</pre>
          <div className="modal-footer">
            {!system && /\.(md|txt)$/i.test(preview.path) ? (
              <button
                className="secondary"
                disabled={busy || draftBusy}
                onClick={() => {
                  const path = preview.path;
                  setPreview(null);
                  void prepareReport(path).catch((e) => notify(e.message));
                }}
              >
                Open as report
              </button>
            ) : null}
            <button className="secondary" onClick={() => setPreview(null)}>
              Close
            </button>
            <button
              className="primary"
              onClick={() => {
                setAttachments((a) =>
                  a.includes(preview.path) ? a : [...a, preview.path],
                );
                setPreview(null);
                setInspectorOpen(false);
              }}
            >
              Use in conversation
              <Plus size={16} />
            </button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  Sparkles,
  Square,
  Check,
  ChevronDown,
  FileSearch,
  ListChecks,
  GitCompareArrows,
  X,
  Terminal,
  CircleHelp,
  FileText,
  Mic,
  Keyboard,
} from "lucide-react";
import { api, type Activity, type Conversation, type Project } from "./api.ts";
import { documentLink } from "./document-links.ts";
import { insertTranscript, nativeVoiceAvailable } from "./voice-draft.ts";
import { TabletActions } from "./Tablet.tsx";
import { useRecovery } from "./use-recovery.ts";
import {
  emptyChat,
  recoverySnapshot,
  recoveryRevision,
  writeRecovery,
  flushRecovery,
  type ChatDraft,
  type Submission,
} from "./recovery-store.ts";

const busyStates = new Set(["running", "starting", "waiting", "stopping"]);
type Props = {
  recoveryKey: string;
  recoveryScope: string;
  consumeRequest: () => void;
  request?: { id: string; text: string } | null;
  project: Project;
  conversation: Conversation | null;
  events: Activity[];
  connected: boolean;
  onNew: () => Promise<Conversation>;
  refresh: () => Promise<void>;
  onPreview: (path: string) => void;
  notify: (message: string) => void;
  onAddToReport: (text: string) => void;
};
function Question({
  event,
  conversationId,
  notify,
}: {
  event: Activity;
  conversationId: string;
  notify: Props["notify"];
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  return (
    <form
      className="question-card"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api(`/conversations/${conversationId}/answer`, "POST", {
            requestId: event.data.requestId,
            answers,
          });
        } catch (error) {
          notify((error as Error).message);
        }
      }}
    >
      <strong>
        <CircleHelp size={18} /> A question before continuing
      </strong>
      {event.data.questions.map((q: any) => (
        <label key={q.id}>
          {q.question}
          <input
            type={q.isSecret ? "password" : "text"}
            value={answers[q.id] || ""}
            onChange={(e) =>
              setAnswers((a) => ({ ...a, [q.id]: e.target.value }))
            }
            list={`options-${q.id}`}
            required
            autoComplete="off"
          />
          <datalist id={`options-${q.id}`}>
            {q.options?.map((o: any) => (
              <option key={o.label} value={o.label}>
                {o.description}
              </option>
            ))}
          </datalist>
        </label>
      ))}
      <button className="primary" type="submit">
        Continue
      </button>
    </form>
  );
}
function CommandApproval({ event, conversationId, notify }: {
  event: Activity;
  conversationId: string;
  notify: Props["notify"];
}) {
  const [busy, setBusy] = useState(false);
  async function resolve(decision: "approve" | "decline") {
    setBusy(true);
    try {
      await api(`/conversations/${conversationId}/command`, "POST", {
        requestId: event.data.requestId,
        decision,
      });
    } catch (error) {
      notify((error as Error).message);
      setBusy(false);
    }
  }
  return <section className="question-card command-card" aria-label="Terminal command approval">
    <strong><Terminal size={18} /> Review terminal command</strong>
    <p>Workspace: {event.data.workspace}</p>
    <pre>{event.data.command}</pre>
    <p>This runs as Termux on the tablet. It can access Termux files, saved sign-ins and the network.</p>
    <div className="command-buttons">
      <button type="button" className="secondary" disabled={busy} onClick={() => void resolve("decline")}>Decline</button>
      <button type="button" className="primary" disabled={busy} onClick={() => void resolve("approve")}>Approve and run</button>
    </div>
  </section>;
}
export function Chat({
  recoveryKey,
  recoveryScope,
  consumeRequest,
  project,
  request,
  conversation,
  events,
  connected,
  onNew,
  refresh,
  onPreview,
  notify,
  onAddToReport,
}: Props) {
  const system = project.kind === "system";
  const assistant = project.kind === "assistant" || project.kind === "meeting";
  const code = project.kind === "code";
  const recovery = useRecovery<ChatDraft>(recoveryKey);
  const draft = recovery.value || emptyChat;
  const { text, attachments, replyStyle } = draft;
  function updateDraft(patch: Partial<ChatDraft>, key = recoveryKey) {
    const latest =
      (recoverySnapshot(key).value as ChatDraft | null) || emptyChat;
    return writeRecovery(key, { ...latest, ...patch });
  }
  const setText = (text: string) => {
    editVersion.current += 1;
    updateDraft({ text });
  };
  const setAttachments = (attachments: string[]) =>
    updateDraft({ attachments });
  const setReplyStyle = (replyStyle: ChatDraft["replyStyle"]) =>
    updateDraft({ replyStyle });
  const [sending, setSending] = useState(false),
    [showActivity, setShowActivity] = useState(false),
    [typing, setTyping] = useState(false),
    [voiceMessage, setVoiceMessage] = useState("");
  const tabletShell = nativeVoiceAvailable(navigator.userAgent, window.location.origin);
  const voiceSession = useRef<{ id: string; key: string; text: string; start: number; end: number; edit: number; revision?: number } | null>(null);
  const voiceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const editVersion = useRef(0);
  const sendingRef = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null),
    cursor = useRef<{ text: string; start: number; end: number } | null>(null),
    bottom = useRef<HTMLDivElement>(null),
    keepFollowing = useRef(true);
  function cancelVoice() {
    if (voiceTimer.current) clearTimeout(voiceTimer.current);
    voiceTimer.current = null;
    const active = voiceSession.current;
    voiceSession.current = null;
    if (active?.id) void api("/voice/cancel", "POST", { id: active.id }).catch(() => {});
  }
  useEffect(() => () => cancelVoice(), [recoveryKey]);
  async function pollVoice(id: string) {
    const active = voiceSession.current;
    if (!active || active.id !== id) return;
    try {
      const result = await api<{ state: string; key?: string; revision?: number; text?: string }>(`/voice/status?id=${encodeURIComponent(id)}`);
      if (voiceSession.current !== active) return;
      if (result.state === "waiting" || result.state === "listening") {
        setVoiceMessage(result.state === "waiting" ? "Opening voice input…" : "Listening…");
        voiceTimer.current = setTimeout(() => void pollVoice(id), 800);
        return;
      }
      voiceSession.current = null;
      if (result.state === "complete" && result.key === recoveryKey && result.text) {
        const current = (recoverySnapshot(recoveryKey).value as ChatDraft | null) || emptyChat;
        if (current.text !== active.text || editVersion.current !== active.edit ||
            recoveryRevision(recoveryKey) !== active.revision || result.revision !== active.revision) {
          setVoiceMessage("Draft changed while listening. Tap Talk to dictate again.");
          return;
        }
        try {
          const { text: next, caret } = insertTranscript(active.text, active.start, active.end, result.text);
          if (!updateDraft({ text: next })) throw new Error("Draft could not be saved. Try Talk again.");
          cursor.current = { text: next, start: caret, end: caret };
          requestAnimationFrame(() => textarea.current?.setSelectionRange(caret, caret));
          setVoiceMessage("Transcript added. Review it before sending.");
        } catch (error) { setVoiceMessage((error as Error).message); }
      } else if (result.state === "canceled") setVoiceMessage("Voice input canceled. Draft kept.");
      else if (result.state === "error") setVoiceMessage("Voice input did not finish. Try Talk again.");
      else setVoiceMessage("Voice input expired. Try Talk again.");
    } catch (error) {
      if (voiceSession.current === active) {
        cancelVoice();
        setVoiceMessage((error as Error).message);
      }
    }
  }
  async function startVoice() {
    if (!tabletShell || !connected || !recovery.ready || voiceSession.current) return;
    const current = (recoverySnapshot(recoveryKey).value as ChatDraft | null) || emptyChat;
    const lastCursor = cursor.current?.text === current.text ? cursor.current : null;
    const start = lastCursor?.start ?? current.text.length;
    const end = lastCursor?.end ?? start;
    const capture: { id: string; key: string; text: string; start: number; end: number; edit: number; revision?: number } =
      { id: "", key: recoveryKey, text: current.text, start, end, edit: editVersion.current };
    voiceSession.current = capture;
    setVoiceMessage("Opening voice input…");
    try {
      await flushRecovery(recoveryKey);
      if (voiceSession.current !== capture) return;
      if (editVersion.current !== capture.edit) {
        voiceSession.current = null;
        setVoiceMessage("Draft changed. Tap Talk again.");
        return;
      }
      capture.revision = recoveryRevision(recoveryKey);
      const result = await api<{ id: string }>("/voice/start", "POST", { key: recoveryKey, revision: capture.revision });
      if (voiceSession.current !== capture) {
        void api("/voice/cancel", "POST", { id: result.id }).catch(() => {});
        return;
      }
      capture.id = result.id;
      void pollVoice(result.id);
    } catch (error) {
      if (voiceSession.current === capture) {
        voiceSession.current = null;
        setVoiceMessage((error as Error).message);
      }
    }
  }
  const followActions = useCallback(() => {
    if (keepFollowing.current)
      bottom.current?.scrollIntoView({ behavior: "instant", block: "end" });
  }, []);
  const busy = busyStates.has(conversation?.status || "");
  const { messages, activity, questions, commands } = useMemo(() => {
    const messages: {
        id: string;
        role: string;
        text: string;
        time: string;
        phase?: string;
      }[] = [],
      byId = new Map<string, number>(),
      activity: Activity[] = [];
    const questions = new Map<string, Activity>();
    const commands = new Map<string, Activity>();
    for (const e of events) {
      if (e.type === "user")
        messages.push({
          id: String(e.seq),
          role: "user",
          text: e.data.text,
          time: e.createdAt,
        });
      else if (
        e.type === "delta" ||
        (e.type === "item" && e.data.type === "agentMessage")
      ) {
        const id = e.data.itemId || e.data.id;
        if (!byId.has(id)) {
          byId.set(id, messages.length);
          messages.push({ id, role: "assistant", text: "", time: e.createdAt });
        }
        const message = messages[byId.get(id)!];
        if (e.type === "item" && e.data.phase) message.phase = e.data.phase;
        if (e.type === "delta") message.text += e.data.text || "";
        else if (e.data.text) message.text = e.data.text;
      } else if (e.type === "question") questions.set(e.data.requestId, e);
      else if (e.type === "question-resolved")
        questions.delete(e.data.requestId);
      else if (e.type === "command-proposal") commands.set(e.data.requestId, e);
      else if (e.type === "command-resolved") commands.delete(e.data.requestId);
      else if (e.type !== "usage" && e.type !== "diff") activity.push(e);
    }
    return { messages, activity, questions: [...questions.values()], commands: [...commands.values()] };
  }, [events]);
  useEffect(() => {
    if (events.length === 0)
      bottom.current
        ?.closest(".chat-scroll")
        ?.scrollTo({ top: 0, behavior: "instant" });
    else if (keepFollowing.current)
      bottom.current?.scrollIntoView({ behavior: "instant", block: "end" });
  }, [events.length]);
  useEffect(() => {
    keepFollowing.current = true;
  }, [conversation?.id, project.id]);
  const handledRequest = useRef("");
  useEffect(() => {
    if (recovery.ready && request && handledRequest.current !== request.id) {
      handledRequest.current = request.id;
      const current = recoverySnapshot(recoveryKey).value as ChatDraft | null;
      updateDraft({
        text: [current?.text, request.text].filter(Boolean).join("\n\n"),
        replyStyle: "standard",
      });
      consumeRequest();
      textarea.current?.focus();
    }
  }, [request?.id, recovery.ready, recoveryKey]);
  async function send(
    value = text,
    style: string = replyStyle,
    keepText = false,
  ) {
    if (
      !recovery.ready ||
      !value.trim() ||
      sendingRef.current ||
      !connected ||
      (busy && style !== "standard")
    )
      return;
    editVersion.current += 1;
    cancelVoice();
    if (draft.pending) {
      notify(
        "Check the previous send before sending another request. Your text is kept here.",
      );
      return;
    }
    sendingRef.current = true;
    setSending(true);
    const composed = attachments.length
      ? `${value.trim()}\n\nSelected files in this workspace:\n${attachments
          .map((f) => `- ${f}`)
          .join("\n")}`
      : value.trim();
    const submission: Submission = {
      id: crypto.randomUUID(),
      text: composed,
      replyStyle: style,
      composerText: text,
      keepText,
    };
    let targetKey = recoveryKey;
    try {
      if (!updateDraft({ pending: submission }))
        throw new Error(
          "Save or copy your text first; recovery storage is unavailable.",
        );
      await flushRecovery(recoveryKey);
      const c = conversation || (await onNew());
      submission.conversationId = c.id;
      targetKey = recoveryScope + c.id;
      if (!updateDraft({ pending: submission }, targetKey))
        throw new Error(
          "The request was not sent because recovery storage is unavailable.",
        );
      await flushRecovery(targetKey);
      const response = await api(
        `/conversations/${c.id}/messages`,
        "POST",
        submission,
      );
      if (
        response.duplicate &&
        ["uncertain", "interrupted"].includes(response.state)
      )
        notify(
          "This message was already submitted and its outcome is uncertain. Review the activity before sending a new request.",
        );
      const latest = recoverySnapshot(targetKey).value as ChatDraft | null;
      updateDraft(
        {
          pending: undefined,
          ...(!keepText && latest?.text === submission.composerText
            ? { text: "", attachments: [] }
            : {}),
        },
        targetKey,
      );
      keepFollowing.current = true;
      await refresh();
    } catch (error) {
      notify((error as Error).message);
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }
  async function checkSubmission() {
    const pending = draft.pending;
    if (!pending || sendingRef.current) return;
    setSending(true);
    try {
      const result = await api(
        `/submissions/${encodeURIComponent(pending.id)}`,
      );
      const latest = recoverySnapshot(recoveryKey).value as ChatDraft | null;
      if (latest?.pending?.id !== pending.id) return;
      if (result.submission) {
        updateDraft({
          pending: undefined,
          ...(!pending.keepText && latest.text === pending.composerText
            ? { text: "", attachments: [] }
            : {}),
        });
        notify(
          `The previous request is recorded (${result.submission.state}). It has not been sent again. Review the conversation before continuing.`,
        );
        await refresh();
      } else {
        updateDraft({ pending: undefined });
        notify(
          "No submission was recorded. Your text is ready; tap Send when you want to continue.",
        );
      }
    } catch (error) {
      notify((error as Error).message);
    } finally {
      setSending(false);
    }
  }
  const prompts = assistant
    ? [
        {
          icon: ListChecks,
          title: "Prepare for tomorrow",
          detail: "Calendar, related mail and a working brief",
          prompt:
            "Check tomorrow’s Outlook calendar for my Council meeting. Read the relevant event and search related emails. Save a meeting brief with proposed outcomes, questions and source links. Clearly flag anything unavailable or uncertain.",
        },
        {
          icon: FileSearch,
          title: "Find an email",
          detail: "Search the accounts already in Outlook",
          prompt: "Search Outlook for emails about ",
        },
        {
          icon: FileText,
          title: "Build a meeting brief",
          detail: "Turn the material into a plan",
          prompt: "Help me prepare a meeting brief. The meeting is about ",
        },
      ]
    : system
      ? [
          {
            icon: FileSearch,
            title: "Check my tablet",
            detail: "Battery, storage and practical improvements",
            prompt:
              "Check this tablet’s health and suggest up to three small, worthwhile improvements. Do not change anything yet.",
          },
          {
            icon: FileSearch,
            title: "Find a file",
            detail: "Look through shared storage",
            prompt: "Find files on my tablet with a name containing ",
          },
          {
            icon: ListChecks,
            title: "Meeting-friendly settings",
            detail: "Screen timeout, brightness and keyboard",
            prompt:
              "Check my tablet settings and suggest small improvements for using it in meetings. Explain the trade-offs before proposing any change.",
          },
        ]
      : [
          {
            icon: FileSearch,
            title: "What needs a decision?",
            detail: "Get to the point before the meeting",
            prompt:
              "What decisions do these documents ask us to make, and what information is still missing?",
          },
          {
            icon: ListChecks,
            title: "What could block this?",
            detail: "Check commitments and open questions",
            prompt:
              "Which commitments or next steps are at risk, based on these sources? Separate documented issues from your analysis.",
          },
          {
            icon: GitCompareArrows,
            title: "Compare documents",
            detail: "See where the story has changed",
            prompt:
              "Compare the documents in this folder. Where do dates, numbers, commitments, or assumptions differ? Cite the documents and explain the differences before suggesting changes.",
          },
        ];
  return (
    <section className="chat-panel" aria-label="Workspace conversation">
      <div
        className="chat-scroll"
        onScroll={(e) => {
          const el = e.currentTarget;
          keepFollowing.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 100;
        }}
      >
        {messages.length === 0 ? (
          <div className="welcome">
            <div className="eyebrow">
              <span className="tiny-star">✦</span> SPACE TO THINK. TOOLS TO ACT.
            </div>
            {assistant ? (
              <h1>
                Start with a thought.
                <br />
                <span>Get ready for what’s next.</span>
              </h1>
            ) : system ? (
              <h1>
                A clearer view
                <br />
                <span>of your tablet.</span>
              </h1>
            ) : (
              <h1>
                A little clarity,
                <br />
                <span>wherever you are.</span>
              </h1>
            )}
            <p>
              {assistant
                ? "Ask about your calendar, find related emails,"
                : system
                  ? "Ask Codex to find a file, check tablet health,"
                  : "Bring your files into the conversation."}
              <br />
              {assistant
                ? "and build your meeting brief in the conversation."
                : system
                  ? "or help with a small settings improvement."
                  : "Ask a question, explore an idea, or make a useful change."}
            </p>
            <div className="context-card">
              <span className="context-icon">
                <FileSearch size={21} />
              </span>
              <div>
                <span className="small-label">YOUR CURRENT WORKSPACE</span>
                <strong>{project.name}</strong>
                <span>{project.description}</span>
              </div>
              <span className="context-badge">
                {assistant
                  ? "Outlook + your files"
                  : system
                    ? "This tablet"
                    : project.kind === "onedrive"
                      ? "OneDrive"
                      : "On this host"}
              </span>
            </div>
            <div className="prompt-grid">
              {prompts.map((p) => (
                <button
                  className="prompt-card"
                  disabled={!recovery.ready}
                  key={p.title}
                  onClick={() => {
                    setText(p.prompt);
                    setReplyStyle("quick");
                    textarea.current?.focus();
                  }}
                >
                  <p.icon size={20} />
                  <strong>{p.title}</strong>
                  <span>{p.detail}</span>
                  <ArrowUp size={16} className="prompt-arrow" />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="messages">
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-author">
                  {message.role === "assistant" ? (
                    <>
                      <Sparkles size={16} /> Galaxy
                    </>
                  ) : (
                    <>
                      <span className="mini-avatar">A</span> You
                    </>
                  )}
                  <time>
                    {new Date(message.time).toLocaleTimeString([], {
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </time>
                </div>
                <div className="markdown">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      table: ({ children }) => (
                        <div className="table-scroll">
                          <table>{children}</table>
                        </div>
                      ),
                      a: ({ href, children }) => {
                        if (href && /^https:\/\//i.test(href))
                          return (
                            <a href={href} target="_blank" rel="noreferrer">
                              {children}
                            </a>
                          );
                        return (
                          <button
                            className="file-link"
                            onClick={() => {
                              if (href) {
                                let target = href.replace(/:\d+(?::\d+)?$/, "");
                                for (const root of [
                                  conversation?.workspace,
                                  project.path,
                                ])
                                  if (root && target.startsWith(root + "/"))
                                    target = target.slice(root.length + 1);
                                const path = documentLink("", target);
                                if (path !== null) onPreview(path);
                              }
                            }}
                          >
                            {children}
                          </button>
                        );
                      },
                    }}
                  >
                    {message.text || "…"}
                  </ReactMarkdown>
                </div>
                {message.role === "assistant" &&
                message.phase !== "commentary" &&
                message.text &&
                !busy ? (
                  <div className="answer-actions">
                    <button
                      className="secondary compact"
                      disabled={sending || !connected}
                      onClick={() =>
                        void send(
                          `Explain this answer further, checking the supporting sources:\n\n${message.text.slice(0, 12000)}`,
                          "explain",
                          true,
                        )
                      }
                    >
                      <CircleHelp size={15} /> Explain further
                    </button>
                    <button
                      hidden={system || assistant || code}
                      className="secondary compact"
                      disabled={sending || !connected}
                      onClick={() => onAddToReport(message.text)}
                    >
                      <FileText size={15} /> Add to report
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
        {system ? (
          <TabletActions
            conversation={conversation}
            revision={events.filter((e) => e.type === "tablet-action").length}
            notify={notify}
            onReady={followActions}
          />
        ) : null}
        {conversation &&
          questions.map((q) => (
            <Question
              key={q.seq}
              event={q}
              conversationId={conversation.id}
              notify={notify}
            />
          ))}
        {conversation && commands.map((command) => <CommandApproval
          key={command.seq}
          event={command}
          conversationId={conversation.id}
          notify={notify}
        />)}
        {busy ? (
          <div className="working">
            <span className="pulse-dot" />
            {conversation?.status === "waiting"
              ? "Waiting for your answer"
              : conversation?.status === "starting"
                ? "Opening your workspace…"
                : "Working on your request…"}
          </div>
        ) : null}
        {activity.length > 0 ? (
          <div className="activity-section">
            <button
              className="activity-toggle"
              onClick={() => setShowActivity(!showActivity)}
            >
              <Terminal size={15} /> Activity & evidence{" "}
              <span>{activity.length}</span>
              <ChevronDown size={16} />
            </button>
            {showActivity ? (
              <div className="activity-list">
                {activity.map((e) => (
                  <div className="activity-row" key={e.seq}>
                    <Check size={14} />
                    <div>
                      {e.type === "command-result" ? (
                        <>
                          <strong>{e.data.command}</strong>
                          <span>{e.data.error || (e.data.timedOut ? "Timed out" : `Exit ${e.data.exitCode}`)}</span>
                          {e.data.stdout ? <pre>{e.data.stdout}</pre> : null}
                          {e.data.stderr ? <pre>{e.data.stderr}</pre> : null}
                          {e.data.truncated ? <span>Output was truncated.</span> : null}
                        </>
                      ) : e.type === "item" ? (
                        <>
                          <strong>
                            {e.data.type === "commandExecution"
                              ? e.data.command
                              : "File changes"}
                          </strong>
                          <span>
                            {e.data.status || e.data.stage}
                            {e.data.exitCode !== undefined &&
                            e.data.exitCode !== null
                              ? ` · exit ${e.data.exitCode}`
                              : ""}
                          </span>
                          {e.data.aggregatedOutput ? (
                            <pre>{e.data.aggregatedOutput}</pre>
                          ) : null}
                          {e.data.changes ? (
                            <pre>{JSON.stringify(e.data.changes, null, 2)}</pre>
                          ) : null}
                        </>
                      ) : (
                        <>
                          <strong>
                            {e.data.text ||
                              e.data.message ||
                              (e.type === "saved"
                                ? `Saved ${e.data.path} to ${e.data.destination}`
                                : e.data.status)}
                          </strong>
                          <span>
                            {new Date(e.createdAt).toLocaleTimeString()}
                          </span>
                          {e.type === "tablet-evidence" ||
                          e.type === "outlook-evidence" ? (
                            <pre>{JSON.stringify(e.data.result, null, 2)}</pre>
                          ) : null}
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        <div ref={bottom} />
      </div>
      <div className="composer-area">
        {recovery.error ? (
          <p className="inline-error" role="alert">
            {recovery.error}
          </p>
        ) : null}
        {draft.pending ? (
          <div className="connection-warning" role="status">
            Previous send awaiting confirmation. It will not be sent
            automatically.{" "}
            <button
              className="secondary compact"
              disabled={sending}
              onClick={() => void checkSubmission()}
            >
              Check previous send
            </button>
          </div>
        ) : text || attachments.length ? (
          <p className="recovery-status" role="status">
            {!recovery.ready
              ? "Checking recovery…"
              : recovery.saving
                ? "Saving recovery copy…"
                : recovery.error
                  ? "Unsent draft · recovery unconfirmed"
                  : "Unsent draft · recovery saved"}
          </p>
        ) : null}
        <div className="composer-heading">
          <label htmlFor="galaxy-question">
            {assistant
              ? "What can I help you prepare?"
              : system
                ? "Ask about this tablet"
                : "Ask about this workspace"}
          </label>
          <button
            className="secondary compact"
            disabled={busy || sending || !connected}
            onClick={() =>
              void send(
                system
                  ? "Check my tablet’s current health and suggest worthwhile improvements."
                  : assistant
                    ? "Check tomorrow’s Outlook calendar and give me a short overview of the meetings to prepare for. Flag any accounts that need sign-in."
                    : "Bring me up to speed on the source material for this meeting.",
                "brief",
                true,
              )
            }
          >
            <Sparkles size={15} />{" "}
            {assistant ? "Tomorrow" : system ? "Check tablet" : "Brief me"}
          </button>
        </div>
        {!connected ? (
          <div className="connection-warning">
            Reconnecting to your workspace. Unsent text stays on this device.
          </div>
        ) : null}
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          {attachments.length ? (
            <div className="attachments">
              {attachments.map((file) => (
                <button
                  type="button"
                  key={file}
                  onClick={() =>
                    setAttachments(attachments.filter((f) => f !== file))
                  }
                >
                  {file}
                  <X size={13} />
                </button>
              ))}
            </div>
          ) : null}
          <div className="composer-input-row">
          <textarea
            id="galaxy-question"
            disabled={!recovery.ready}
            ref={textarea}
            aria-label="Message Galaxy"
            value={text}
            inputMode={tabletShell && !typing ? "none" : "text"}
            onChange={(e) => {
              setText(e.target.value);
              cursor.current = { text: e.target.value, start: e.target.selectionStart, end: e.target.selectionEnd };
            }}
            onSelect={(e) => {
              cursor.current = { text: e.currentTarget.value, start: e.currentTarget.selectionStart, end: e.currentTarget.selectionEnd };
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={
              busy
                ? "Add context or steer this request…"
                : tabletShell
                  ? "Ask a question. Tap Talk to dictate…"
                  : "Ask a question, or dictate with your keyboard’s microphone…"
            }
            rows={2}
            maxLength={14000}
          />
          {tabletShell ? (
            <div className="composer-input-actions">
              <button type="button" className="composer-talk" aria-label="Talk to Galaxy"
                disabled={!connected || !recovery.ready || !!voiceSession.current}
                onClick={() => void startVoice()}><Mic size={19} /><span>Talk</span></button>
              <button type="button" className="composer-type" aria-label={typing ? "Hide keyboard" : "Show keyboard"}
                onClick={() => {
                  if (typing) { setTyping(false); textarea.current?.blur(); }
                  else {
                    setTyping(true);
                    if (textarea.current) textarea.current.inputMode = "text";
                    textarea.current?.focus();
                  }
                }}><Keyboard size={18} /><span>{typing ? "Hide" : "Type"}</span></button>
            </div>
          ) : null}
          </div>
          {tabletShell && voiceMessage ? <div className="voice-status" role="status">
            <span>{voiceMessage}</span>
            {voiceSession.current ? <button type="button" onClick={() => {
              cancelVoice();
              setVoiceMessage("Voice input canceled. Draft kept.");
            }}>Cancel</button> : null}
          </div> : null}
          <div className="composer-footer">
            <label className="answer-style">
              <span className="sr-only">Answer style</span>
              <select
                aria-label="Answer style"
                value={replyStyle}
                disabled={busy || sending || !recovery.ready}
                onChange={(e) =>
                  setReplyStyle(e.target.value as "quick" | "standard")
                }
              >
                <option value="quick">Quick answers</option>
                <option value="standard">Full conversation</option>
              </select>
            </label>
            <div>
              {busy ? (
                <button
                  type="button"
                  className="stop-button"
                  onClick={async () => {
                    try {
                      await api(
                        `/conversations/${conversation?.id}/stop`,
                        "POST",
                        {},
                      );
                      await refresh();
                    } catch (e) {
                      notify((e as Error).message);
                    }
                  }}
                >
                  <Square size={13} /> Stop
                </button>
              ) : null}
              <button
                type="submit"
                className="send-button"
                aria-label={busy ? "Send guidance" : "Send message"}
                disabled={
                  !text.trim() ||
                  sending ||
                  !connected ||
                  (busy && replyStyle !== "standard")
                }
              >
                <ArrowUp size={20} />
              </button>
            </div>
          </div>
        </form>
        <div className="composer-note">
          <span>
            Sources:{" "}
            {attachments.length
              ? `${attachments.length} selected file${attachments.length === 1 ? "" : "s"} in `
              : ""}
            {project.name}
            {assistant
              ? " · saved locally"
              : conversation?.mode === "draft"
                ? " · draft copy"
                : ""}
          </span>
          <kbd>Ctrl ↵</kbd>
        </div>
      </div>
    </section>
  );
}

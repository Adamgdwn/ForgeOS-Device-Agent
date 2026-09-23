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
} from "lucide-react";
import { api, type Activity, type Conversation, type Project } from "./api.ts";
import { documentLink } from "./document-links.ts";
import { TabletActions } from "./Tablet.tsx";
import { useRecovery } from "./use-recovery.ts";
import {
  emptyChat,
  recoverySnapshot,
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
  const recovery = useRecovery<ChatDraft>(recoveryKey);
  const draft = recovery.value || emptyChat;
  const { text, attachments, replyStyle } = draft;
  function updateDraft(patch: Partial<ChatDraft>, key = recoveryKey) {
    const latest =
      (recoverySnapshot(key).value as ChatDraft | null) || emptyChat;
    return writeRecovery(key, { ...latest, ...patch });
  }
  const setText = (text: string) => updateDraft({ text });
  const setAttachments = (attachments: string[]) =>
    updateDraft({ attachments });
  const setReplyStyle = (replyStyle: ChatDraft["replyStyle"]) =>
    updateDraft({ replyStyle });
  const [sending, setSending] = useState(false),
    [showActivity, setShowActivity] = useState(false);
  const sendingRef = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null),
    bottom = useRef<HTMLDivElement>(null),
    keepFollowing = useRef(true);
  const followActions = useCallback(() => {
    if (keepFollowing.current)
      bottom.current?.scrollIntoView({ behavior: "instant", block: "end" });
  }, []);
  const busy = busyStates.has(conversation?.status || "");
  const { messages, activity, questions } = useMemo(() => {
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
      else if (e.type !== "usage" && e.type !== "diff") activity.push(e);
    }
    return { messages, activity, questions: [...questions.values()] };
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
                      hidden={system || assistant}
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
                      {e.type === "item" ? (
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
          <textarea
            id="galaxy-question"
            disabled={!recovery.ready}
            ref={textarea}
            aria-label="Message Galaxy"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={
              busy
                ? "Add context or steer this request…"
                : "Ask a question, or dictate with your keyboard’s microphone…"
            }
            rows={2}
            maxLength={14000}
          />
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

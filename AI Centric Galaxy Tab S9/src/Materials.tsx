import { useRef, useState } from "react";
import { Cloud, FilePlus2, Mail, X } from "lucide-react";
import { api, type Project } from "./api.ts";
import {
  documentByteLimit,
  MAX_BATCH_BYTES,
  DOCUMENT_LIMIT_MESSAGE,
} from "../shared/document-limits.ts";

export function Materials({
  project,
  conversationId,
  done,
  cloud,
  close,
}: {
  project?: Project;
  conversationId?: string;
  done: (project: Project) => Promise<void>;
  cloud: (project: Project) => Promise<void>;
  close: () => void;
}) {
  const [name, setName] = useState("Meeting report"),
    [files, setFiles] = useState<File[]>([]);
  const [email, setEmail] = useState({
    subject: "",
    from: "",
    to: "",
    date: "",
    text: "",
  });
  const [mode, setMode] = useState<"files" | "email">("files"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const request = useRef<{ fingerprint: string; id: string } | null>(null);
  const hasMaterial = files.length > 0 || email.text.trim().length > 0;
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
  async function importFiles() {
    if (
      files.length > 50 ||
      files.some((f) => f.size > documentByteLimit(f.name)) ||
      files.reduce((s, f) => s + f.size, 0) > MAX_BATCH_BYTES
    )
      throw new Error(DOCUMENT_LIMIT_MESSAGE);
    const uploads = [];
    for (const file of files) {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () =>
          reject(new Error(`Could not read ${file.name}. Select it again.`));
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.readAsDataURL(file);
      });
      uploads.push({ name: file.name, data });
    }
    const payload = {
      name,
      projectId: project?.id,
      conversationId,
      files: uploads,
      email: email.text.trim() ? email : undefined,
    };
    const fingerprint = JSON.stringify(payload);
    if (request.current?.fingerprint !== fingerprint)
      request.current = { fingerprint, id: crypto.randomUUID() };
    await done(
      await api<Project>("/materials", "POST", {
        ...payload,
        id: request.current.id,
      }),
    );
  }
  return (
    <div className="materials-form">
      <p>
        Add copies of the material for this assignment. Originals stay in place.
      </p>
      {!project ? (
        <label>
          Workspace name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
          />
        </label>
      ) : (
        <p className="destination-label">
          Adding to <strong>{project.name}</strong>
          {conversationId ? " and this conversation" : ""}
        </p>
      )}
      <button
        className="secondary wide-button"
        disabled={busy || (!project && !name.trim())}
        onClick={() =>
          void run(async () =>
            cloud(
              project || (await api<Project>("/workspaces", "POST", { name })),
            ),
          )
        }
      >
        <Cloud size={18} /> Choose OneDrive files
      </button>
      <div className="material-tabs" aria-label="Material type">
        <button
          className={mode === "files" ? "active" : ""}
          onClick={() => setMode("files")}
        >
          <FilePlus2 size={17} /> Documents & saved emails
        </button>
        <button
          className={mode === "email" ? "active" : ""}
          onClick={() => setMode("email")}
        >
          <Mail size={17} /> Paste an email
        </button>
      </div>
      {mode === "files" ? (
        <div className="upload-area">
          <label>
            Choose files on this device
            <input
              type="file"
              multiple
              accept=".docx,.pdf,.txt,.md,.csv,.tsv,.json,.eml"
              disabled={busy}
              onChange={(e) => {
                const chosen = Array.from(e.target.files || []);
                setFiles((previous) => [...previous, ...chosen]);
                e.target.value = "";
              }}
            />
          </label>
          <p>
            Word, PDF, text, Markdown, CSV, JSON and .eml emails. Supported
            email attachments are included. For Outlook .msg messages, paste the
            email instead.
          </p>
        </div>
      ) : (
        <div className="email-fields">
          <label>
            Subject
            <input
              value={email.subject}
              onChange={(e) => setEmail({ ...email, subject: e.target.value })}
              maxLength={500}
            />
          </label>
          <div className="field-pair">
            <label>
              From
              <input
                value={email.from}
                onChange={(e) => setEmail({ ...email, from: e.target.value })}
                maxLength={500}
              />
            </label>
            <label>
              To
              <input
                value={email.to}
                onChange={(e) => setEmail({ ...email, to: e.target.value })}
                maxLength={500}
              />
            </label>
          </div>
          <label>
            Date (as shown in the email)
            <input
              value={email.date}
              onChange={(e) => setEmail({ ...email, date: e.target.value })}
              maxLength={500}
            />
          </label>
          <label>
            Email or email thread
            <textarea
              value={email.text}
              onChange={(e) => setEmail({ ...email, text: e.target.value })}
              maxLength={200000}
              rows={8}
              placeholder="Paste the message, including any earlier replies you want assessed."
            />
          </label>
          <p>
            This saves a source document the assistant can refer back to. It
            does not connect to your inbox.
          </p>
        </div>
      )}
      {files.length ? (
        <ul className="selected-materials">
          {files.map((f, i) => (
            <li key={i}>
              <span>{f.name}</span>
              <button
                className="icon-button"
                aria-label={`Remove selected ${f.name}`}
                disabled={busy}
                onClick={() => setFiles((all) => all.filter((_, n) => n !== i))}
              >
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {email.text.trim() && mode !== "email" ? (
        <p>
          <Mail size={14} /> Pasted email included:{" "}
          {email.subject || "Untitled"}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="inline-error">
          {error}
        </p>
      ) : null}
      <div className="material-actions">
        <button className="secondary" disabled={busy} onClick={close}>
          Cancel
        </button>
        <button
          className="primary"
          disabled={
            busy || (!project && !name.trim()) || (!!project && !hasMaterial)
          }
          onClick={() =>
            void run(async () =>
              hasMaterial
                ? importFiles()
                : done(await api<Project>("/workspaces", "POST", { name })),
            )
          }
        >
          {busy
            ? "Adding material…"
            : hasMaterial
              ? "Add to workspace"
              : "Create workspace"}
        </button>
      </div>
      <p className="muted">
        New material is available here and in future conversations. Other
        existing drafts keep their earlier snapshots.
      </p>
    </div>
  );
}

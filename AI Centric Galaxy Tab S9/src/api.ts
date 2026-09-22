export async function api<T = any>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers:
      method === "GET"
        ? {}
        : { "Content-Type": "application/json", "X-Galaxy-Request": "1" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const result = await response.json();
  if (response.status === 401)
    window.dispatchEvent(new Event("galaxy-unpaired"));
  if (!response.ok)
    throw new Error(
      result.error || "The workstation could not complete this request.",
    );
  return result;
}
export type Project = {
  id: string;
  name: string;
  path: string;
  kind: "local" | "onedrive" | "system" | "assistant" | "meeting";
  description: string;
};
export type Conversation = {
  id: string;
  projectId: string;
  title: string;
  workspace: string;
  mode: string;
  status: string;
  createdAt: string;
  updatedAt: string;
};
export type Activity = {
  seq: number;
  type: string;
  data: any;
  createdAt: string;
};
export type FileEntry = {
  name: string;
  path: string;
  directory: boolean;
  size: number;
};
export type Account = {
  slot: number;
  label: string;
  username: string | null;
  status: string;
  error?: string;
  source?: "host";
  readOnly?: boolean;
  connectionId?: string;
  login?: { code?: string; url?: string; expires?: number };
};
export type Bootstrap = {
  runtime?: "tablet" | "workstation";
  projects: Project[];
  conversations: Conversation[];
  accounts: Account[];
  microsoftConfigured: boolean;
  host: {
    available: boolean;
    compatible: boolean;
    version: string;
    activeConversation: string | null;
  };
};

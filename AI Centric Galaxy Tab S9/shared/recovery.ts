export type Submission = {
  id: string;
  text: string;
  replyStyle: string;
  conversationId?: string;
  composerText: string;
  keepText: boolean;
};
export type ChatDraft = {
  kind: "chat";
  text: string;
  attachments: string[];
  replyStyle: "quick" | "standard";
  pending?: Submission;
};
export type ReportDraft = {
  kind: "report";
  text: string;
  hash: string;
  path: string;
};
export type Draft = ChatDraft | ReportDraft;
export const emptyChat: ChatDraft = {
  kind: "chat",
  text: "",
  attachments: [],
  replyStyle: "standard",
};
export function validRecovery(value: any): value is Draft {
  if (!value || typeof value.text !== "string" || value.text.length > 500_000)
    return false;
  if (value.kind === "report")
    return (
      typeof value.hash === "string" &&
      value.hash.length <= 100 &&
      typeof value.path === "string" &&
      value.path.length <= 2000
    );
  return (
    value.kind === "chat" &&
    value.text.length <= 14000 &&
    ["quick", "standard"].includes(value.replyStyle) &&
    Array.isArray(value.attachments) &&
    value.attachments.length <= 50 &&
    value.attachments.every(
      (p: unknown) => typeof p === "string" && p.length <= 2000,
    ) &&
    (!value.pending ||
      (typeof value.pending.id === "string" &&
        value.pending.id.length <= 100 &&
        typeof value.pending.text === "string" &&
        value.pending.text.length <= 16000 &&
        ["quick", "standard", "brief"].includes(value.pending.replyStyle) &&
        typeof value.pending.composerText === "string" &&
        value.pending.composerText.length <= 14000 &&
        typeof value.pending.keepText === "boolean" &&
        (value.pending.conversationId === undefined ||
          typeof value.pending.conversationId === "string")))
  );
}

export type ReplyStyle = "standard" | "quick" | "brief" | "explain";

export function replyStyle(value: unknown): ReplyStyle {
  if (value === undefined) return "standard";
  if (
    typeof value === "string" &&
    ["standard", "quick", "brief", "explain"].includes(value)
  )
    return value as ReplyStyle;
  throw new Error("Choose quick answers or a full conversation.");
}

export function meetingRequest(text: string, style: ReplyStyle): string {
  if (style === "standard") return text;
  const format = {
    quick:
      "Answer the specific question first, in at most three short sentences (about 100 words maximum), plus a short supporting quotation when useful. Do not give a general folder audit unless asked.",
    brief:
      "Give a one-minute briefing, aiming for 180 words and no more than 250. Use these four headings in order: What this is about; Decisions needed; Key numbers and commitments; Three questions to ask. Include exactly three useful questions. If no decision is documented, say so. Do not include a preamble or a full document-by-document audit.",
    explain:
      "Explain the selected answer in more depth, with the supporting evidence, assumptions, conflicts and information still needed. Keep it focused on that answer.",
  }[style];
  return `${text}\n\nMeeting answer guidance:\n${format} Read the relevant source files and SOURCE_INDEX.md before answering. Search only this workspace (or the selected files, if provided); describe the actual sources checked in a short final 'Sources checked' line with clickable, workspace-relative Markdown links. Cite factual claims using the source filename and document date when available; do not mistake a file modification date for a document date. Quote accurately and sparingly. If the sources do not answer the question, say 'I couldn't find that in these sources' and identify what is missing. Distinguish documented facts from your analysis. State conflicts and unreadable or truncated sources. Do not infer approval, ownership, dates or completion from missing evidence. This is a read-only question: answer in chat, without writing or editing any files.`;
}

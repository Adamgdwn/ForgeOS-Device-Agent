export const documentTypes: Record<string, string> = {
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  pdf: "application/pdf",
  txt: "text/plain",
  md: "text/markdown",
  csv: "text/csv",
  tsv: "text/tab-separated-values",
  json: "application/json",
  eml: "message/rfc822",
};
export function documentType(path: string) {
  const extension = path.split(".").at(-1)?.toLowerCase() || "";
  return Object.hasOwn(documentTypes, extension)
    ? documentTypes[extension]
    : undefined;
}

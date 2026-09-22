export const MAX_BATCH_BYTES = 25_000_000;
export function documentByteLimit(name: string) {
  return /\.(pdf|docx)$/i.test(name) ? 20_000_000 : 8_000_000;
}
export const DOCUMENT_LIMIT_MESSAGE =
  "Choose up to 50 files: Word/PDF up to 20 MB, other files up to 8 MB, and 25 MB total.";

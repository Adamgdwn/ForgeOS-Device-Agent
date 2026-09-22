import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  existsSync,
  chmodSync,
} from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const STATE = resolve(
  process.env.GALAXY_STATE_DIR || resolve(ROOT, ".local"),
);
export const PORT = Number(process.env.GALAXY_PORT || 4318);
export const TABLET_RUNTIME = process.env.GALAXY_RUNTIME === "android";
export const ORIGIN = process.env.GALAXY_ORIGIN || `http://localhost:${PORT}`;
export const CODEX_VERSION = "codex-cli 0.154.0-alpha.6.2";
export const TURN_TIMEOUT_MS = 10 * 60 * 1000;
mkdirSync(STATE, { recursive: true, mode: 0o700 });
chmodSync(STATE, 0o700);
export function privateWrite(path: string, content: string | Buffer) {
  writeFileSync(path, content, { mode: 0o600 });
  chmodSync(path, 0o600);
}
export type ExistingMicrosoft = {
  cliPath: string;
  connectionName: string;
  username: string;
  userId: string;
  driveId: string;
  label: string;
};
export function readSettings(): {
  microsoftClientId?: string;
  existingMicrosoft?: ExistingMicrosoft;
} {
  const path = resolve(STATE, "settings.json");
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {};
}
export function setExistingMicrosoft(connection?: ExistingMicrosoft) {
  privateWrite(
    resolve(STATE, "settings.json"),
    JSON.stringify({ ...readSettings(), existingMicrosoft: connection }),
  );
}
export function setMicrosoftClientId(clientId: string) {
  if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(clientId))
    throw new Error("Enter a valid Microsoft application (client) ID.");
  privateWrite(
    resolve(STATE, "settings.json"),
    JSON.stringify({ ...readSettings(), microsoftClientId: clientId }),
  );
}

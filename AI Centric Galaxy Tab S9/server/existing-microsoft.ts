import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { realpathSync } from "node:fs";
import { isAbsolute } from "node:path";
import { TABLET_RUNTIME } from "./config.ts";
import type { ExistingMicrosoft } from "./config.ts";

const exec = promisify(execFile);
const graph = "https://graph.microsoft.com/v1.0";
type Connection = { name: string; connectedAs: string; active: boolean };
type Runner = (cliPath: string, args: string[]) => Promise<unknown>;
async function runCli(cliPath: string, args: string[]): Promise<unknown> {
  // Only a trusted host command configures this path. No executable, arguments,
  // credentials or environment variables are accepted from the browser.
  const env: NodeJS.ProcessEnv = {};
  for (const key of ["HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PATH", "SystemRoot", "TEMP", "TMP"])
    if (process.env[key]) env[key] = process.env[key];
  try {
    const { stdout } = await exec(TABLET_RUNTIME ? "/data/data/com.termux/files/usr/bin/node" : process.execPath, [cliPath, ...args, "--output", "json"], {
      env, timeout: 45_000, killSignal: "SIGKILL", maxBuffer: 2_000_000,
      windowsHide: true,
    });
    return JSON.parse(stdout);
  } catch {
    // exec errors include stdout/stderr, which can contain credentials.
    throw new Error("The existing Microsoft CLI connection is unavailable. Check its sign-in on this device.");
  }
}

export class ExistingMicrosoftClient {
  runner: Runner;
  fetcher: typeof fetch;
  private queue: Promise<unknown> = Promise.resolve();
  constructor(fetcher: typeof fetch = fetch, runner: Runner = runCli) {
    this.fetcher = fetcher;
    this.runner = runner;
  }
  private serial<T>(action: () => Promise<T>): Promise<T> {
    const result = this.queue.then(action);
    this.queue = result.catch(() => {});
    return result;
  }
  private async credentials(cliPath: string, binding?: ExistingMicrosoft) {
    const connections = await this.runner(cliPath, ["connection", "list"]);
    if (!Array.isArray(connections)) throw new Error("Microsoft CLI returned no account list.");
    const active = connections.filter((c: Connection) => c.active);
    if (active.length !== 1 || !active[0].name || !active[0].connectedAs)
      throw new Error("Sign in to Microsoft CLI on this device first.");
    const connection = active[0] as Connection;
    if (binding && (connection.name !== binding.connectionName ||
      connection.connectedAs.toLowerCase() !== binding.username.toLowerCase()))
      throw new Error("The active Microsoft account changed. Restore the linked account or reconnect it from this device.");
    const token = await this.runner(cliPath, ["util", "accesstoken", "get", "--resource", "https://graph.microsoft.com"]);
    if (typeof token !== "string" || !token || /\s/.test(token))
      throw new Error("Microsoft CLI did not return a usable access token.");
    // Validate the identity using the SAME token as the eventual file request.
    // This catches account switches between the CLI list and token commands.
    const profile = await this.json("/me?$select=id,userPrincipalName,mail", token);
    if (!profile.id || (binding ? profile.id !== binding.userId :
      ![profile.userPrincipalName, profile.mail].some((email) =>
        typeof email === "string" && email.toLowerCase() === connection.connectedAs.toLowerCase())))
      throw new Error("Microsoft returned a different identity. Reconnect the intended account from this host.");
    return { connection, token, profile };
  }
  private async json(path: string, token: string) {
    let response: Response;
    try {
      response = await this.fetcher(graph + path, {
        headers: { Authorization: `Bearer ${token}` },
        redirect: "error", signal: AbortSignal.timeout(30_000),
      });
    } catch {
      throw new Error("Microsoft could not verify this linked connection. Try again shortly.");
    }
    if (!response.ok)
      throw new Error(`Microsoft could not verify this linked connection (${response.status}). Check its sign-in and OneDrive access.`);
    return await response.json() as Record<string, any>;
  }
  async inspect(path: string, label: string): Promise<ExistingMicrosoft> {
    if (!isAbsolute(path)) throw new Error("Use the absolute path to the Microsoft CLI executable.");
    const cliPath = realpathSync(path);
    if (!cliPath.endsWith(".js")) throw new Error("Use the Microsoft CLI JavaScript entry point (or its executable symlink).");
    return this.serial(async () => {
      const { connection, token, profile } = await this.credentials(cliPath);
      const drive = await this.json("/me/drive?$select=id,driveType", token);
      if (!drive.id) throw new Error("This account has no accessible OneDrive.");
      return { cliPath, connectionName: connection.name, username: connection.connectedAs,
        userId: profile.id, driveId: drive.id, label: label.trim().slice(0, 60) || connection.connectedAs };
    });
  }
  token(binding: ExistingMicrosoft): Promise<string> {
    return this.serial(async () => (await this.credentials(binding.cliPath, binding)).token);
  }
}

import { spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import { TABLET_RUNTIME } from "./config.ts";

export const COMMAND_TIMEOUT_MS = 60_000;
const OUTPUT_LIMIT = 32_000;

export function validateWorkspaceCommand(value: unknown): string {
  if (typeof value !== "string" || !value.trim() || value.length > 2_000)
    throw new Error("Use a command under 2,000 characters.");
  if (/[\x00-\x08\x0b-\x1f\x7f\u202a-\u202e\u2066-\u2069]/u.test(value))
    throw new Error("The command contains hidden control characters.");
  return value;
}

export type CommandResult = {
  command: string;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  truncated: boolean;
  timedOut: boolean;
};

/** A command runs with Termux's app identity only after a separate UI approval. */
export async function runWorkspaceCommand(
  workspace: string,
  command: string,
  signal?: AbortSignal,
): Promise<CommandResult> {
  if (!TABLET_RUNTIME)
    throw new Error("Tablet commands are available only on the tablet.");
  validateWorkspaceCommand(command);
  const cwd = realpathSync(workspace);
  return await new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error("The command was stopped."));
    const child = spawn(
      "/data/data/com.termux/files/usr/bin/timeout",
      ["--signal=TERM", "--kill-after=3s", "60s",
       "/data/data/com.termux/files/usr/bin/bash", "--noprofile", "--norc", "-c", command],
      {
        cwd,
        detached: true,
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          HOME: cwd,
          PWD: cwd,
          PATH: "/data/data/com.termux/files/usr/bin:/system/bin",
          LANG: "C.UTF-8",
          TMPDIR: cwd,
        },
      },
    );
    let stdout = "", stderr = "", truncated = false, timedOut = false;
    const append = (which: "stdout" | "stderr", data: Buffer) => {
      const current = which === "stdout" ? stdout : stderr;
      const available = Math.max(0, OUTPUT_LIMIT - stdout.length - stderr.length);
      const chunk = data.toString("utf8");
      const next = chunk.slice(0, available);
      if (next.length < chunk.length) truncated = true;
      if (which === "stdout") stdout = current + next;
      else stderr = current + next;
    };
    child.stdout.on("data", (data: Buffer) => append("stdout", data));
    child.stderr.on("data", (data: Buffer) => append("stderr", data));
    const kill = () => {
      if (!child.pid) return;
      try { process.kill(-child.pid, "SIGTERM"); } catch { /* already stopped */ }
      setTimeout(() => {
        try { process.kill(-child.pid!, "SIGKILL"); } catch { /* already stopped */ }
      }, 1_000).unref();
    };
    const timer = setTimeout(() => { timedOut = true; kill(); }, COMMAND_TIMEOUT_MS);
    const abort = () => kill();
    signal?.addEventListener("abort", abort, { once: true });
    child.on("error", (error) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      resolve({ command, exitCode: code, stdout, stderr, truncated, timedOut: timedOut || code === 124 });
    });
  });
}

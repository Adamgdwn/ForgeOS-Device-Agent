import {
  readFileSync,
  readdirSync,
  lstatSync,
  realpathSync,
  statfsSync,
} from "node:fs";
import { resolve, basename } from "node:path";
import { STATE } from "./config.ts";
import { visible } from "./files.ts";

export async function nativeDevice(
  operation: string,
  fields: Record<string, unknown> = {},
) {
  const key = readFileSync(resolve(STATE, "device-bridge.key"), "utf8");
  if (!/^[0-9a-f]{64}$/.test(key))
    throw new Error("Device tools are not configured.");
  let response: Response;
  try {
    response = await fetch("http://127.0.0.1:48442/device", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ operation, ...fields }),
      signal: AbortSignal.timeout(7000),
      redirect: "error",
    });
  } catch {
    throw new Error(
      "Enable Galaxy Device Tools in Android Accessibility settings, then check the connection again.",
    );
  }
  if (!response.ok) throw new Error("Device tools are unavailable.");
  const text = await response.text();
  if (text.length > 700000)
    throw new Error("Device response exceeded its limit.");
  const data = JSON.parse(text);
  if (data.error) throw new Error(data.error);
  return data.result as Record<string, any>;
}
function shared(path: string) {
  if (
    !path.startsWith("/storage/emulated/0/") &&
    path !== "/storage/emulated/0"
  )
    throw new Error("Choose shared tablet storage.");
  if (
    path
      .slice(20)
      .split("/")
      .filter(Boolean)
      .some((p) => !visible(p) || p === "Android" || p === "..")
  )
    throw new Error("Private paths are excluded.");
  if (realpathSync(path) !== path)
    throw new Error("Symbolic links are excluded.");
  return path;
}
export function nativeFile(path: string) {
  return readFileSync(shared(path));
}
export async function nativeShell(args: string[]): Promise<string> {
  const [command, ...rest] = args;
  if (command === "getprop")
    return (await nativeDevice("property", { name: rest[0] })).value;
  if (command === "dumpsys" && rest[0] === "battery")
    return (await nativeDevice("battery")).value;
  if (command === "cat" && rest[0] === "/proc/meminfo")
    return (await nativeDevice("memory")).value;
  if (command === "pm" && rest.join(" ") === "list packages -3")
    return (await nativeDevice("apps")).value;
  if (command === "settings")
    return (
      await nativeDevice("setting", {
        action: rest[0],
        name: rest[2],
        value: rest[3],
      })
    ).value;
  if (command === "df") {
    const s = statfsSync(STATE);
    return `Filesystem 1K-blocks Used Available\n/data ${(s.blocks * s.bsize) / 1024} ${((s.blocks - s.bfree) * s.bsize) / 1024} ${(s.bavail * s.bsize) / 1024}`;
  }
  if (command === "realpath") return shared(rest[0]);
  if (command === "stat") {
    const s = lstatSync(shared(rest.at(-1)!));
    return `${s.isFile() ? "regular file" : "other"}|${s.size}`;
  }
  if (command === "find") {
    const root = shared(rest[0]),
      depth = Number(rest[rest.indexOf("-maxdepth") + 1]);
    if (![1, 6].includes(depth)) throw new Error("Unsupported search depth.");
    const rows: string[] = [];
    let visited = 0;
    const walk = (folder: string, level: number) => {
      for (const entry of readdirSync(folder, { withFileTypes: true })) {
        if (++visited > 8000)
          throw new Error("That search is too broad. Choose a smaller folder.");
        if (
          !visible(entry.name) ||
          entry.name === "Android" ||
          entry.isSymbolicLink()
        )
          continue;
        const path = resolve(folder, entry.name);
        let stat;
        try {
          stat = lstatSync(path);
        } catch {
          continue;
        }
        if (stat.isFile() || stat.isDirectory())
          rows.push(
            `${stat.isDirectory() ? "drwx------" : "-rw-------"}\t${stat.size}\t${stat.mtimeMs / 1000}\t${path}\0`,
          );
        if (stat.isDirectory() && level < depth)
          try {
            walk(path, level + 1);
          } catch (e) {
            if (visited > 8000) throw e;
          }
      }
    };
    walk(root, 1);
    return rows.join("");
  }
  throw new Error("Unsupported on-device operation.");
}

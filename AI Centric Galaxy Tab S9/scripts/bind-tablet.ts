import { execFileSync } from "node:child_process";
import { privateWrite } from "../server/config.ts";
import { TABLET_BINDING } from "../server/tablet.ts";
const serial = process.argv[2];
if (!serial || !/^[A-Za-z0-9._:-]{1,100}$/.test(serial))
  throw new Error("Usage: ./galaxy bind-tablet ADB_SERIAL");
const adb = (args: string[]) =>
  execFileSync("adb", ["-s", serial, ...args], {
    encoding: "utf8",
    timeout: 5000,
  }).trim();
if (adb(["get-state"]) !== "device")
  throw new Error("Connect and authorize the tablet first.");
const model = adb(["shell", "getprop", "ro.product.model"]);
if (!/^SM-X81/.test(model))
  throw new Error("This pilot expects a Galaxy Tab S9 Plus.");
privateWrite(TABLET_BINDING, JSON.stringify({ serial, model }));
console.log(`Linked ${model} to the permanent System workspace.`);

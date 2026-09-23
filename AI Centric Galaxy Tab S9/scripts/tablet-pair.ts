// Called only by the launcher's fixed Termux command. The single-use result
// travels through an explicit PendingIntent, never a URL, clipboard or web view.
import { randomBytes, createHash } from "node:crypto";
import { privateWrite } from "../server/config.ts";
import { NATIVE_TICKET_FILE } from "../server/auth.ts";
const ticket = randomBytes(32).toString("base64url");
privateWrite(
  NATIVE_TICKET_FILE,
  JSON.stringify({
    hash: createHash("sha256").update(ticket).digest("hex"),
    expires: Date.now() + 60_000,
  }),
);
process.stdout.write(ticket);

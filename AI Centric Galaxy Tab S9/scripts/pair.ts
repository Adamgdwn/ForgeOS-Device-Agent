import { readFileSync } from "node:fs";
import { PAIR_FILE, rotatePairCode } from "../server/auth.ts";
import { Store } from "../server/store.ts";
if (process.argv.includes("--rotate")) {
  rotatePairCode();
  const store = new Store();
  store.db.exec("DELETE FROM sessions");
  store.close();
}
// Intentionally shown only by an operator running the local pairing command.
console.log(`Galaxy pairing code: ${readFileSync(PAIR_FILE, "utf8").trim()}`);

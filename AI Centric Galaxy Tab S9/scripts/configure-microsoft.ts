import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { readSettings, setMicrosoftClientId } from "../server/config.ts";
import { Store } from "../server/store.ts";

// Developer provisioning stays on the trusted host, outside the tablet UI.
export function configureMicrosoft(clientId: string, store: Store) {
  const current = readSettings().microsoftClientId;
  if (current === clientId) return;
  if (current)
    throw new Error("Microsoft sign-in is already configured. Replacing its registration requires a deliberate host migration.");
  if (store.db.prepare("SELECT slot FROM accounts WHERE status NOT IN ('disconnected', 'removed') OR homeId IS NOT NULL").get())
    throw new Error("Disconnect existing OneDrive sign-ins before configuring their registration.");
  setMicrosoftClientId(clientId);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const store = new Store();
  try {
    configureMicrosoft(process.argv[2]?.trim() || "", store);
    console.log("Microsoft sign-in is configured. Refresh Connections and use Sign in with Microsoft for each account.");
  } catch (error) {
    console.error((error as Error).message);
    process.exitCode = 1;
  } finally {
    store.close();
  }
}

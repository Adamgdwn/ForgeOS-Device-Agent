import { ExistingMicrosoftClient } from "../server/existing-microsoft.ts";
import { setExistingMicrosoft } from "../server/config.ts";

try {
  const [path, label = "Existing Microsoft account"] = process.argv.slice(2);
  if (!path) throw new Error('Usage: ./galaxy connect-existing /absolute/path/to/microsoft365 "Account name"');
  const connection = await new ExistingMicrosoftClient().inspect(path, label);
  setExistingMicrosoft(connection);
  console.log(`Linked ${connection.username} as ${connection.label}. Browse and import are enabled; cloud save is disabled for this connection.`);
} catch (error) {
  console.error((error as Error).message);
  process.exitCode = 1;
}

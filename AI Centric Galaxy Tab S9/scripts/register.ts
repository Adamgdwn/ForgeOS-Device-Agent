import { realpathSync, statSync } from "node:fs";
import { basename } from "node:path";
import { Store } from "../server/store.ts";
const path = process.argv[2];
if (!path) {
  console.error(
    'Usage: npm run register -- "/absolute/folder" "Workspace name"'
  );
  process.exit(1);
}
const root = realpathSync(path);
if (!statSync(root).isDirectory()) throw new Error("Choose a folder.");
const store = new Store();
const project = store.addProject({
  name: process.argv[3] || basename(root),
  path: root,
  kind: "local",
  description: "Local workstation folder",
});
console.log(`Registered ${project.name}. Refresh Galaxy Workspace to open it.`);
store.close();

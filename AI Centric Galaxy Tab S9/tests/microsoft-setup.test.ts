import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

const state = mkdtempSync(resolve(tmpdir(), "galaxy-microsoft-setup-"));
process.env.GALAXY_STATE_DIR = state;
const { configureMicrosoft } = await import("../scripts/configure-microsoft.ts");
const { readSettings } = await import("../server/config.ts");
const { Store } = await import("../server/store.ts");
const { OneDrive } = await import("../server/onedrive.ts");
const id = "00000000-0000-4000-8000-000000000001";

test("host provisioning preserves linked accounts and refuses registration replacement", () => {
  const linked = { label: "Existing host fixture" };
  writeFileSync(resolve(state, "settings.json"), JSON.stringify({ existingMicrosoft: linked }));
  const store = new Store(":memory:");
  try {
    assert.throws(() => new OneDrive(store).client(1), /person setting up Galaxy Workspace/);
    assert.throws(() => configureMicrosoft("not-an-id", store), /valid Microsoft/);
    assert.equal(readSettings().microsoftClientId, undefined);
    for (const status of ["connecting", "connected"]) {
      store.db.prepare("UPDATE accounts SET status=? WHERE slot=1").run(status);
      assert.throws(() => configureMicrosoft(id, store), /Disconnect existing/);
    }
    store.db.prepare("UPDATE accounts SET status='disconnected', homeId='existing-user' WHERE slot=1").run();
    assert.throws(() => configureMicrosoft(id, store), /Disconnect existing/);
    store.db.prepare("UPDATE accounts SET homeId=NULL WHERE slot=1").run();
    store.db.prepare("UPDATE accounts SET status='removed' WHERE slot=2").run();
    configureMicrosoft(id, store);
    configureMicrosoft(id, store);
    assert.equal(readSettings().microsoftClientId, id);
    assert.deepEqual(readSettings().existingMicrosoft, linked);
    assert.throws(() => configureMicrosoft("00000000-0000-4000-8000-000000000002", store), /deliberate host migration/);
    assert.equal(readSettings().microsoftClientId, id);
  } finally {
    store.close();
  }
});

test.after(() => rmSync(state, { recursive: true, force: true }));

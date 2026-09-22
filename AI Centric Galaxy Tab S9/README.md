# Galaxy Workspace

Last Updated: 2026-09-22

Galaxy Workspace is an independent tablet workspace for document assessment, meeting preparation and interactive reports. Its native Android launcher opens a React workspace backed by Node, SQLite and Codex **on the Galaxy Tab S9+ itself**. The tablet needs internet for AI and cloud services; it does not need a laptop, USB tether or Tailscale.

This is a locally installed, single-user pilot. It does not root or flash the tablet and is independent of the parent ForgeOS runtime.

## Use it

Open **Galaxy Workspace → Open workspace**. The launcher starts its local Termux engine. Look for **Running on this tablet** and **On-device tools connected**.

- **Assistant:** discuss an upcoming meeting, read the existing Outlook calendar and relevant mail, gather dated source snapshots, and save a named meeting brief. Outlook comes forward during reading; keep the tablet unlocked. Sign-in and partial-coverage warnings remain visible. Opening mail may mark it read.
- **Workspaces:** gather selected OneDrive files, Android documents and pasted/saved emails. Ask for a summary, compare sources, discuss findings and refine an isolated report. Quick answers and briefings are read-only; Full conversation supports requested draft changes.
- **Reports:** edit beside chat; preserve source links; export Word, PDF or Markdown. Cloud publication requires an explicit destination and action.
- **System:** inspect tablet health, installed applications and shared-storage files. Four supported settings use proposal, Apply, read-back and conditional Undo.
- **Connections:** independent Microsoft sign-ins plus the migrated existing CLI connection. Both current connected accounts passed live root browsing on the tablet. The reused CLI connection supports reads/imports and local drafts; cloud writes remain disabled for it.

The installed packages are Galaxy Workspace **0.3.0**, Galaxy Device Tools **0.2.0**, and Termux. Keep Termux installed: it holds the runtime, saved work and local Codex sign-in. Voice typing uses the tablet keyboard; Google voice typing is enabled, but actual spoken accuracy needs the user's test.

Read the [user guide](docs/2026-09-22%20-%20User%20Guide.md), [deployment runbook](docs/2026-09-22%20-%20Runbook.md), [Android implementation](docs/2026-09-22%20-%20Android%20App.md), [design and boundaries](docs/2026-09-22%20-%20Design%20and%20Boundaries.md), and [verification record](docs/2026-09-22%20-%20Verification.md).

## Develop and verify

The workstation remains the build surface. Use Node 24.14 or later; npm dependencies are locked. Android builds discover the existing SDK and use the checksum-pinned Gradle wrapper.

```sh
npm ci
./galaxy build
./galaxy test
./galaxy android-build
```

The Android build runs APK assembly, seven launcher/transfer-policy tests and lint, with a ten-minute timeout and one Gradle worker. The parent `bash scripts/governance-preflight.sh` is required before substantial changes.

The standalone runtime is under Termux's `~/galaxy-workspace`. `scripts/tablet-engine.sh` starts the local service; `scripts/tablet-codex.sh` supplies Android compatibility for the pinned official Codex client, `codex-cli 0.154.0-alpha.6.2`. PRoot supplies a resolver-file binding, not a security sandbox. Every Android worker has shell tools disabled and receives only its typed workspace, Assistant or System tools. Each turn is bounded to ten minutes; only one turn runs at a time.

The optional workstation mode still uses `./galaxy start`, `./galaxy register /absolute/folder 'Name'`, and `./galaxy pair`. Its legacy `android-install` command adds USB reverse forwarding; **do not use it for the independent tablet deployment**. Use `adb install -r` for APK updates and preserve Termux's private state. Detailed provisioning and recovery are in the runbook.

## Practical limits

Outlook access reads its visible UI, not a complete mailbox/calendar export. Account synchronization, cached events, screen lock and organizational restrictions can limit it. The September 22 sign-in warning concerned an unused campaign account, not the Council account, as Adam clarified. That account is not required for field testing. Current meeting details still need confirmation from the relevant calendar and emails.

Actual OneDrive publication/conflict behavior, a full day of battery/network switching, stylus/DeX use and speech recognition remain field tests. Offline AI, arbitrary terminal control, spreadsheet editing, OCR and formatting-preserving Office edits are not implemented. The repository contains source and synthetic fixtures; all credentials, real documents, databases, APKs and private verification evidence are ignored.

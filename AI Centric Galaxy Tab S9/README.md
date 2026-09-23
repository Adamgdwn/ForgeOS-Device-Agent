# Galaxy Workspace

Last Updated: 2026-09-23

Galaxy Workspace is an independent tablet workspace for document assessment, meeting preparation and interactive reports. Its native Android launcher opens a React workspace backed by Node, SQLite and Codex **on the Galaxy Tab S9+ itself**. The tablet needs internet for AI and cloud services; it does not need a laptop, USB tether or Tailscale.

This is a locally installed, single-user pilot. It does not root or flash the tablet and is independent of the parent ForgeOS runtime.

## Use it

Open **Galaxy Voice Preview → Open workspace** on this tablet. The launcher starts its local Termux engine. Look for **Running on this tablet** and **On-device tools connected**.

- **Assistant:** discuss an upcoming meeting, read the existing Outlook calendar and relevant mail, gather dated source snapshots, and save a named meeting brief. Outlook comes forward during reading; keep the tablet unlocked. Sign-in and partial-coverage warnings remain visible. Opening mail may mark it read.
- **Workspaces:** gather selected OneDrive files, Android documents and pasted/saved emails. Ask for a summary, compare sources, discuss findings and refine an isolated report. Quick answers and briefings are read-only; Full conversation supports requested draft changes.
- **Code workspace:** choose **New workspace → Create code workspace** for a persistent on-tablet folder. Codex can read and edit plain-text files there in Full conversation. Each terminal command appears in a review card and runs only after you tap **Approve and run**. Commands execute as Termux and can access its private files, saved sign-ins and network; the command is not sandboxed to the workspace. Decline any command you do not want to run.
- **Reports:** edit beside chat, recover unfinished edits, and export Word, PDF or Markdown. Previous exports retain their version and save receipts. Cloud publication requires an explicit destination and action.
- **Office files:** import and discuss Word, Excel and PowerPoint; open originals/copies in the installed Android apps. Open, Save a copy and Share a copy are available from document previews and report exports. Re-import Office edits explicitly with Add material.
- **System:** inspect tablet health, installed applications and shared-storage files. Four supported settings use proposal, Apply, read-back and conditional Undo.
- **Connections:** independent Microsoft sign-ins plus the migrated existing CLI connection. Both current connected accounts passed live root browsing on the tablet. The reused CLI connection supports reads/imports and local drafts; cloud writes remain disabled for it.

The tablet has **Galaxy Voice Preview 0.4.1-preview**, **Galaxy Device Tools Preview 0.3.0-preview**, and Termux. Open **Galaxy Voice Preview → Open workspace** to try the in-composer **Talk** button. Tapping the message field keeps the on-screen keyboard closed; **Type** opens it when needed. Talk opens Google's installed speech panel and is designed to add recognized words to the unsent draft. Adam reported one successful spoken phrase; full voice-to-chat acceptance remains open. The preview shares the existing local engine and saved work. Keep Termux installed: it holds the runtime, saved work and local Codex sign-in. The original Galaxy Workspace 0.4.0 and Device Tools 0.2.0 remain installed but disabled because this laptop's debug signing key cannot update them. The new Device Tools Preview needs Accessibility enabled and Battery set to Unrestricted on this Samsung tablet for reliable Outlook reading.

**Continue development:** start with the [current tablet code harness turnover](docs/2026-09-23%20-%20Tablet%20Code%20Harness%20Turnover.md), then the [voice-first Assistant plan and Windows handoff](docs/2026-09-23%20-%20Voice%20First%20Assistant%20and%20Windows%20Handoff.md) for earlier history and the meeting workflow. Git transfers source and instructions, not the tablet's private work or sign-ins. Native Windows runtime parity remains unverified.

Read the [user guide](docs/2026-09-22%20-%20User%20Guide.md), [deployment runbook](docs/2026-09-22%20-%20Runbook.md), [Android implementation](docs/2026-09-22%20-%20Android%20App.md), [design and boundaries](docs/2026-09-22%20-%20Design%20and%20Boundaries.md), and [verification record](docs/2026-09-22%20-%20Verification.md).

The [executive workflow plan](docs/2026-09-22%20-%20Executive%20Workflow%20Plan.md) maps meeting preparation, document editing, filing, sharing and Windows handoff against the current implementation. It prioritizes unsaved-text recovery, native document handoffs, complete document reading and portable workspaces. Recovery, local re-pairing, original-file downloads, native Open/Save/Share, export history and Excel/PowerPoint text previews are delivered in 0.4.0. Full long-document reading, revision association, folder shortcuts and portable workspaces remain planned.

## Develop and verify

The workstation remains the build surface. Use Node 24.14 or later; npm dependencies are locked. Android builds discover the existing SDK and use the checksum-pinned Gradle wrapper.

```sh
npm ci
./galaxy build
./galaxy test
./galaxy android-build
```

The Android build runs APK assembly, eight launcher/transfer-policy tests and lint, with a ten-minute timeout and one Gradle worker. The parent `bash scripts/governance-preflight.sh` is required before substantial changes.

The standalone runtime is under Termux's `~/galaxy-workspace`. `scripts/tablet-engine.sh` starts the local service; `scripts/tablet-codex.sh` supplies Android compatibility for the pinned official Codex client, `codex-cli 0.154.0-alpha.6.2`. PRoot supplies a resolver-file binding, not a security sandbox. Android's built-in Codex shell stays disabled. The opt-in Code workspace has a typed command tool with per-command user approval; document, Assistant and System workers keep their existing typed tools. Each turn is bounded to ten minutes; only one turn runs at a time.

The optional workstation mode still uses `./galaxy start`, `./galaxy register /absolute/folder 'Name'`, and `./galaxy pair`. Its legacy `android-install` command adds USB reverse forwarding; **do not use it for the independent tablet deployment**. Use `adb install -r` for APK updates and preserve Termux's private state. Detailed provisioning and recovery are in the runbook.

## Practical limits

Outlook access reads its visible UI, not a complete mailbox/calendar export. Account synchronization, cached events, screen lock and organizational restrictions can limit it. The September 22 sign-in warning concerned an unused campaign account, not the Council account, as Adam clarified. That account is not required for field testing. Current meeting details still need confirmation from the relevant calendar and emails.

Actual OneDrive publication/conflict behavior, a full day of battery/network switching, stylus/DeX use and speech recognition remain field tests. Offline AI, sandboxed terminal execution, OCR and Office editing inside Galaxy are not implemented. XLSX previews show stored cells/formulas, not recalculated values; PPTX previews show text/notes, not visual slide analysis. Extracted text remains capped at 100,000 characters. Use Excel, PowerPoint and Word for editing and save a copy before re-importing. Office editing depends on the account’s entitlement. The repository contains source and synthetic fixtures; all credentials, real documents, databases, APKs and private verification evidence are ignored.

# Galaxy tablet code harness turnover

Last Updated: 2026-09-23
Status: installed on Adam's Galaxy Tab S9+ for a local pilot; development paused at Adam's request

## Read this first

The active source is `AI Centric Galaxy Tab S9` on branch
`galaxy/voice-preview-2026-09-23` in
`https://github.com/Adamgdwn/ForgeOS-Device-Agent.git`. Implementation commit
`c102920` adds the on-tablet Code workspace. This note is the current operational
handoff; the older [voice-first Assistant and Windows handoff](2026-09-23%20-%20Voice%20First%20Assistant%20and%20Windows%20Handoff.md)
retains the development history and meeting-workflow plan, but its original
"Start here on Windows" order predates the installed previews and code harness.

Adam's current product direction is a small on-tablet Codex harness: persistent
conversations and selected workspaces, file reading and editing, terminal commands,
plus a few tablet and Office tools. Meeting preparation is one optional use.
Workspace commands and edits are intended to run on the tablet. Voice is an input
method for the same conversation.

## What is installed and working

- Open **Galaxy Voice Preview** (`com.adamgoodwin.galaxyworkspace.voicepreview`,
  0.4.1-preview) and tap **Open workspace**. The native launcher starts the
  independent Termux engine at `127.0.0.1:4318`. The last restart showed
  **Running on this tablet** and **Codex ready**. No laptop connection is needed
  for normal use.
- **Galaxy Device Tools Preview**
  (`com.adamgoodwin.galaxyreader.voicepreview`, 0.3.0-preview) supplies the
  reviewed tablet and Outlook operations. Its Accessibility service is enabled;
  Adam set its Battery mode to **Unrestricted**, and the whitelist read-back
  confirmed it. The older original Galaxy and Device Tools packages remain
  installed with their data but are disabled for Android user 0, avoiding the
  duplicate app instances. This laptop's debug key cannot update those original
  packages. Do not uninstall them or clear Termux data to work around signing.
- **Tablet Code** is an existing, persistent Code workspace in Termux's private
  `.local/workspaces/<uuid>` tree. It has `README.md` made by Codex through the
  typed `workspace_edit` tool. The app can create more Code workspaces from
  **New workspace → Create code workspace**. File listing/reading and direct
  plain-text edits are available in **Full conversation**. Edits require the
  current file hash and reject hidden/credential-named and symlink paths.
- A `workspace_command` proposal appears in the chat with the exact command and
  selected workspace. Each command waits for a fresh **Approve and run** tap.
  Adam approved `pwd`; the recorded exit code was 0 and stdout matched the
  `Tablet Code` path. A second approval of that proposal is rejected. Declined,
  stopped or restart-interrupted proposals do not execute. The built-in Codex
  shell remains disabled on Android; Assistant, System and document workspaces
  retain their restricted typed tools.
- After the final server/UI deployment, the native launcher restarted the engine.
  `Tablet Code`, its `README.md`, the chat and the command result remained visible.
  The app was still running at the end of this session. Temporary deployment
  files under `/data/local/tmp/galaxy-code-stage` were removed.
- Google voice input was selected. Adam reported that a spoken phrase worked.
  The Galaxy Talk/Type controls were visible in prior device checks; full
  voice-to-chat and rotation/recovery acceptance is still outstanding.

## Trust boundary and known limits

An approved command runs under **Termux's app identity**, with a 60-second
supervisor and bounded output. It is **not confined to the selected workspace**:
it can reach Termux private files, saved sign-ins and the network. The approval
card states this. Review the actual command every time; there is no blanket
approval. A command interrupted after approval by an engine crash can have an
uncertain side effect, so inspect the workspace before retrying it.

The first live `pwd` result reached Codex, but Codex took several minutes to
finish its reply until a follow-up asked it to conclude. A prompt instruction to
answer promptly after simple commands is installed, but that specific latency
fix has not yet been retested. More complex command sequences, Git operations,
and long sessions are also unverified. `Tablet Code` and conversation history are
local to Termux; GitHub does **not** automatically sync them. The repository
contains source and synthetic tests, not the tablet's SQLite history, files,
Microsoft/Codex sessions or signing material.

The Assistant Outlook reader now scopes searches to an exact visible account,
including scrolling the account picker, and verifies the selected scope. One
live `itinerary` probe submitted in the City account with zero visible results;
it did **not** answer Adam's original Thursday/Friday itinerary request. Keep
source coverage and unrelated-account warnings distinct. Opening mail can mark
it read. The OneDrive meeting workflow remains a separate unfinished story.

## Verification and state preservation

- `npm run build` and `npm run check` passed after the final code changes.
  Focused code-workspace, Assistant, workspace-tools and recovery tests passed.
  The full `npm test` run still fails on this Windows host because some existing
  tests require symlinks/POSIX shell/Python/document converters. The parent
  governance preflight was attempted but its Bash script had CRLF problems on
  this Windows checkout; prior accepted Windows tooling gap is recorded in the
  older handoff. No governance exceptions are open. No Android APK rebuild was
  needed for the final server/UI-only code harness change.
- The installed server and built UI files were copied only after conversations
  were idle/complete; key host/device SHA-256 hashes matched. The native app
  restarted the engine and the live UI checks above passed. `git diff --check`
  passed before implementation commit `c102920` was pushed.
- Before that code deployment, a consistent private SQLite backup passed
  `quick_check=ok` at
  `/data/data/com.termux/files/home/galaxy-backups/2026-09-23-code-harness/before-state.sqlite`.
  Earlier voice/account-scope backups are also in `~/galaxy-backups`. A previous
  bridge key was rotated; **do not restore an older backup's bridge key** over
  the current pairing. Never copy `.local/`, account caches, logs, backups or
  tablet files into Git.
- The tablet was last observed at 14% and charging over USB. Wireless debugging
  was paired and used during development; its IP/port may change. USB and
  wireless ADB addressed the same tablet. Galaxy itself needs neither ADB nor
  the laptop to run.

## Resume safely

1. In a checkout, inspect `git status`, switch to
   `galaxy/voice-preview-2026-09-23`, and `git pull --ff-only` if clean. Read
   `AGENTS.md`, `project-control.yaml`, this note and the deployment runbook.
   Preserve unrelated work; never reset a dirty checkout to force a pull.
2. On the tablet, open **Galaxy Voice Preview → Open workspace**. Confirm
   **Running on this tablet**, **Codex ready**, the saved **Tablet Code** chat
   and `README.md`. If development access is needed, use `adb devices -l` to
   identify the current USB/wireless serial; do not assume the old wireless
   endpoint persists. Check for an active turn before touching the engine.
3. Prioritize the slow post-command reply: reproduce with a harmless approved
   command, inspect the recorded `command-result` and Codex item/turn events,
   then fix and retest response completion. Keep the exact per-command gate.
4. Add a deliberate GitHub checkout/sync flow for Code workspaces if Adam wants
   cross-device source editing there. Verify the actual tablet Git tooling and
   authentication method first; never place credentials in commands, approval
   cards, logs or Git. Do not imply local `Tablet Code` files have synced.
5. Continue voice end-to-end and Assistant/OneDrive work after the general
   harness is reliable. Use synthetic data for acceptance checks before live
   account actions. Preserve the preview package signing distinction and
   Termux's `.local/` state during any deployment.

Adam does not need to do anything now. The next session can resume from the
existing tablet app and this pushed branch.

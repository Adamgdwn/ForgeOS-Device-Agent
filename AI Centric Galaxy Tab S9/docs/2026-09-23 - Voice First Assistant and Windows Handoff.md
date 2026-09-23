# Voice-first Assistant and Windows handoff

Last Updated: 2026-09-23
Status: implementation plan and development handoff; 0.4.1 voice preview active, original 0.4.0 disabled on this tablet

For the current installed state and next-session steps, read the
[tablet code harness turnover](2026-09-23%20-%20Tablet%20Code%20Harness%20Turnover.md)
first. The original implementation order later in this document predates the
on-tablet Code workspace.

September 23 Windows continuation: the Galaxy 0.4.1 source now has an in-composer
Talk action using Android's speech recognition intent, a Type toggle, and an
authenticated local handoff bound to the session, conversation recovery key and
saved draft revision. It never sends the transcript automatically. The web and
Android builds, Android unit tests/lint, and focused voice session tests pass on
Windows. The full npm suite has unrelated Windows toolchain failures (Python,
POSIX shell and document converters). This laptop's debug certificate differs
from the installed 0.4.0 certificate. A separate `Galaxy Voice Preview`
(`com.adamgoodwin.galaxyworkspace.voicepreview`, 0.4.1-preview) was built with
`-PgalaxyPreview=true` and installed beside 0.4.0. Its native launcher paired
with the same local Termux engine and preserved the existing saved work. The
engine received only `server/main.ts`, `server/voice.ts` and `dist`; private
`.local/`, dependencies, scripts and documents were not replaced. A private
pre-update backup is at
`/data/data/com.termux/files/home/galaxy-backups/2026-09-23-voice-preview/before-code-and-state.tar.gz`.

Tablet checks: the preview showed Talk and Type in portrait and landscape;
tapping the field in portrait left the on-screen keyboard closed; Talk opened
Google's speech panel; backing out returned to the unchanged draft without
relaunching the panel. A first native parser build treated JSON `null` as the
string `"null"` and reopened speech repeatedly; this was corrected and the
preview reinstalled. A spoken transcript has not yet been verified on the
tablet. The original 0.4.0 remains installed and the new controls are gated to
0.4.1 or later. Updating that original package still requires its old signing
key. Never uninstall it or replace Termux's private state to bypass signing.
On September 23, after both apps appeared in recent apps, the original
`com.adamgoodwin.galaxyworkspace` package was disabled for Android user 0 with
`adb shell pm disable-user --user 0 com.adamgoodwin.galaxyworkspace`. The
preview was brought to the front, and it remained running with Talk and Type
visible and the keyboard closed. The old package and its data remain installed;
`adb shell pm enable com.adamgoodwin.galaxyworkspace` reverses the change.

Later September 23 Assistant continuation: Adam's live test asked for City inbox
itinerary and plans for Thursday and Friday. The conversation used the default
Quick answers style. Outlook search forced All Accounts, surfaced a sign-in
warning for a different account (`connect@adamgoodwin.ca`), and the turn hit its
ten-minute limit without a complete answer. Adam clarified that his City account
is `Adam.Goodwin@reddeer.ca`; the Outlook search picker visibly lists it. The
installed Codex client reported GPT-6 Astra at medium reasoning effort. The
failure was in account selection, evidence handling and response flow. New chats
now default to Full conversation. Assistant tools discover visible Outlook
accounts and accept an exact account for search; the reader verifies and returns
the selected scope. The instructions require account-specific evidence, correct
handling of warnings from other accounts, both requested dates and a timely
summary when coverage is incomplete. Focused Assistant/Python tests and the web
build pass. The full npm suite still fails on unrelated Windows prerequisites
such as `python3`, POSIX `sh` and document converters.
The picker now waits for late account rows; a scoped search discards warnings
seen before switching accounts and confirms the selected account before entering
the query. The latest reader preview APK was reinstalled successfully. The
updated Python reader script was copied to Termux and its SHA-256 matched the
host copy.
The parent governance preflight was attempted on Windows through temporary LF
copies of its CRLF shell scripts. Its Python test phase showed Windows failures
and was stopped after prolonged execution; the earlier governance preflight
pass and the previously accepted Windows tooling gap remain the basis for this
pilot change. No project-control exceptions are open.

This laptop also cannot update the existing Device Tools 0.2.0 APK because its
debug signature differs. `Galaxy Device Tools Preview` 0.3.0-preview
(`com.adamgoodwin.galaxyreader.voicepreview`) is installed beside it with the
same reviewed typed operations and the search-account picker. The old Device
Tools package was disabled for Android user 0; its data remains installed.
An earlier setup diagnostic accidentally printed the old loopback key in tool
output. It was rotated immediately; the replacement was installed in
Termux and both private helper stores, and the tablet identity binding updated.
Do not restore the older September 23 backup's bridge key over this setup. The
private backup taken after rotation and before the Assistant code update is at
`/data/data/com.termux/files/home/galaxy-backups/2026-09-23-account-scope/before-code-and-state.tar.gz`.
The tablet engine received only `server/assistant.ts`, `scripts/outlook-ui.py`,
`shared/recovery.ts` and `dist`; private `.local/` and workspaces were preserved.
Accessibility for the new helper is enabled. Samsung froze it while its Battery
setting remained Optimized. Adam manually selected Unrestricted; Android's
device-idle whitelist read-back showed the new helper in the user whitelist.
The existing frozen process was then unfrozen with `cmd activity unfreeze` and
the helper answered an authenticated identity probe. The preview helper
received the old helper's system-setting grants for its existing reviewed tools;
the old package remains disabled.
The tablet briefly reported 5% battery while connected through the computer;
subsequent readings showed positive charging current. Paired wireless ADB
connected to the same tablet so the USB cable can be moved to a wall charger.
The user's Google voice input and the Galaxy engine do not require ADB.

Live Outlook verification exposed an account picker that shows only the first
four email rows until scrolled. When the picker is open, Outlook removes its
search-account spinner from the accessibility tree. The reader now scrolls only
the verified account ListView and selects only an exact email row inside it,
then checks the selected scope before submitting a search. A live on-tablet
probe listed `Adam.Goodwin@reddeer.ca`, selected that exact account and submitted
`itinerary`; it reported zero visible result items and one unrelated account
sign-in warning, with no City sign-in warning. This proves account scoping and
submission, not that the requested Thursday/Friday itinerary was found. The
updated reader APK and Python script were installed; their host/device script
hashes matched. The idle engine was restarted through Galaxy's native Open
workspace action; the UI showed Running on this tablet and On-device tools
connected. No user conversation or message was submitted by the probe.

Adam clarified the product direction after this test: Galaxy should be a thin
on-tablet Codex harness with persistent conversations, selected directories,
workspaces and a few tablet/Office tools. Codex should be able to edit files and
run workspace commands, as in its terminal or VS Code interface. The present
tablet worker does not meet that expectation: it disables shell tools and
confines edits to a small set of typed draft/report operations. Assistant's
meeting-specific flow must become an optional specialization rather than the
main interaction model. Voice is an input method for this general conversation.

Do not equate an Android `workspaceWrite` policy value with a working sandbox.
The installed Codex bundles Bubblewrap, but an on-tablet probe of Bubblewrap
failed because Android denied `/proc/sys/kernel/overflowuid`; a read-only
Landlock ABI probe returned ENOSYS. PRoot is only a resolver compatibility
layer. Termux also holds Codex and Microsoft sessions.
The command/edits requirement therefore needs an execution boundary or an
explicitly reviewed trust model before shell tools are enabled. Preserve the
existing Assistant/System read-only behavior while that design is implemented
and tested. The tablet and Windows laptop share a local subnet; paired wireless
ADB connected successfully to the same serial, allowing wall charging during
development without changing Galaxy's independent runtime.

Later September 23 code workspace continuation: Adam explicitly asked to
proceed with the on-tablet Codex harness. An opt-in Code workspace is now
created from the Galaxy UI under Termux's private `.local/workspaces` folder.
Its Codex worker keeps the built-in shell disabled. Typed tools provide file
listing/reading, hash-checked direct plain-text edits under visible paths, and
terminal command proposals. A proposed exact command is persisted to the chat
and requires a fresh in-app Approve and run tap; decline, stop and restart
resolve it without execution. Approved commands run as Termux through a
60-second `timeout` supervisor, with minimal environment and bounded captured
output. This is an explicit trust model, not an OS sandbox: a command can read
Termux's private work and sign-ins and can use the network. The approval card
states that risk. `workspace_edit` cannot access hidden, credential-named or
symlinked paths. Assistant, System and document workspaces retain their prior
tools and restrictions. The subproject risk tier was reassessed as high.

The Windows build and focused code/Assistant/recovery tests passed. The full
npm suite still has pre-existing Windows failures for symlinks and missing
POSIX/Python/document tools. The source and built web assets were copied to the
tablet after an idle-state check and private SQLite backup; hashes for the key
server files and entry HTML matched. The native Galaxy launcher restarted the
engine. Through the live UI, `Tablet Code` was created; Codex used the
`workspace_edit` tool to create `README.md` and completed the turn. A second
turn proposed `pwd` and waited. Adam tapped Approve and run; the recorded
command result had exit code 0 and stdout equal to the selected workspace
path. Codex took several minutes after the command result and finished only
after a short user steer asking it to conclude; the Code workspace instructions
now ask it to answer promptly after a simple command. This verifies one code
edit and one approved terminal command on-device, while response latency and
more complex command workflows remain field tests.
Baseline: Galaxy Workspace 0.4.0, commit `d1abc1c`+
## What Adam wants

Open Galaxy, speak or type naturally, gather relevant information, discuss it,
and put useful work in the right place. Do not make Adam organize the app before
he can ask for help. Keep the existing clear visual design, Office integration
and independent tablet runtime. Voice is the preferred input, with typing and
documents always available. Avoid adding a dashboard full of controls.

The representative request is:

> I have a meeting tomorrow with Minister Newdorf. Compile the relevant material,
> put it in an appropriate folder in my OneDrive under City Council work and
> meetings, and let's discuss how we want the meeting to go.

This is a product example, not an instruction to read live mail or publish files
during this handoff. Verify the person's spelling, meeting date and identity from
the actual event when executing it. Resolve “tomorrow” using the device's local
date and timezone at that time; do not bake this document's date into the feature.

## Findings checked on September 23

- The installed tablet is the authorized SM-X810. Samsung Keyboard is its default.
  Google voice typing is enabled and Google's recognition service is configured.
  Gboard is not installed. These are settings checks, not a successful spoken test.
- `src/Chat.tsx` has a normal textarea and a placeholder referring to the keyboard
  microphone. There is no Galaxy microphone control or recording implementation.
  Enabling a speech service does not establish that its control is visible or
  convenient when Adam taps this field. His report remains an unresolved defect.
- `src/App.tsx` presents “Workspace,” “YOUR WORKSPACES,” and a global conversation
  history together. These labels obscure where to start and which saved work a
  conversation belongs to.
- `server/assistant.ts` already offers typed Outlook reading and local meeting
  brief creation. Saving a brief registers its meeting workspace and moves the
  current conversation into it. Preserve that useful continuity.
- Assistant has no tools for discovering OneDrive folders, importing selected
  cloud material, or publishing a brief. Manual UI browsing/import/export exists.
  Connecting those operations into the discussion is substantive missing work.
- `OneDrive.publishNew` requires a connected writable identity, an existing parent
  folder and a new filename; it refuses conflicts and returns a receipt. There is
  no conversational create-folder operation. The linked CLI account is read-only.
- The tablet is independent. Git contains application source and synthetic tests;
  private documents, SQLite history, account sessions, build outputs and signing
  material are excluded. Pulling Git on Windows will not bring that private state.

## The intended everyday flow

1. Open into **Assistant**, ready to talk or type, with a small **Recent work**
   list. Offer resume for unfinished work; do not silently send recovered text.
2. Tap one clearly visible **Talk** control, dictate, review/correct the transcript,
   and send. Keep the normal keyboard and attachment action alongside it.
3. Galaxy identifies the relevant calendar event and reads related visible mail.
   It reports missing access or partial coverage in ordinary language. Ask one
   focused question only when a material ambiguity prevents progress.
4. Find candidate Council folders in authorized OneDrive connections. Show the
   actual account and folder breadcrumb in the conversation, with a short reason
   for the suggested destination. Reuse a previously chosen Council folder when
   its identity and permissions still match. Do not infer Council ownership from
   an account card called Personal or from the unused campaign account.
5. Gather relevant documents into an isolated local work folder with source links
   and capture/version details. Produce a first brief: purpose, useful background,
   proposed outcomes, questions and unresolved points. Save useful partial work
   when a source is unavailable, clearly marking what is missing.
6. Discuss changes in that same conversation: “Make the funding issue the first
   item,” “What are we missing?”, “Give me a two-minute version.” Update the same
   brief and retain the user's edits with the existing conflict checks.
7. Present one inline **Save to OneDrive** action with account, complete path,
   filename and formats. For a new meeting folder, include the proposed folder
   in this review. Preserve the existing explicit publication boundary; do not
   turn natural-language folder suggestions into silent cloud writes.
8. After an actual confirmed save, show **Saved to [account / path]** and a working
   link. An uncertain upload stays uncertain and is reconciled before retrying.
   Word/PDF exports and the original Office files remain available to open.
9. On Windows, open that same verified OneDrive deliverable in Office. Continuing
   the complete chat/history across devices is a separate, still-planned portable
   workspace feature; never imply that saving a DOCX synchronizes the conversation.

Optional later refinement: **Read reply aloud**, off by default for meetings.
The first release is push-to-talk dictation plus normal discussion, not an
always-listening or full-duplex voice session. Use the installed speech provider
without introducing a paid transcription subscription; do not promise offline
recognition without testing that device/provider combination.

## Explain the organization once, then get it out of the way

User-facing explanation: **A work folder holds the documents and saved brief for
an assignment. A conversation is the discussion about that work. Start talking;
Galaxy can create the work folder when there is something to keep.**

Proposed presentation:

| Current concept | Proposed presentation | Behavior |
| --- | --- | --- |
| Assistant workspace | Assistant | Default starting point; no setup form before asking |
| Your workspaces | My work | Named assignments/meetings with files and report |
| Global Conversations list | Chats within the selected work; Recent work on Assistant | Show parent work title whenever a chat appears outside its work folder |
| New workspace | New work folder, secondary action | Still available for deliberate document collection |
| New conversation | New chat | Explain that it starts another discussion in the current work folder |
| System workspace | Tablet tools | Retain permanent tablet inspection/settings access separately |

The app's “work folder” is a saved assignment, not necessarily a OneDrive folder.
Show its real storage state: **On this tablet**, **Ready to save**, or a verified
OneDrive destination. UI label changes need not rename database tables, IDs or
existing project paths. Keep old links, recovered drafts and saved conversations.
New chats must list the work's available sources/report, but must not pretend to
remember every previous chat unless that context has actually been supplied.

## Implementation order and completion checks

### 1. Fix voice input and simplify the entry screen

First reproduce the missing keyboard microphone on the actual tablet, with and
without the physical keyboard, in portrait and landscape. Check toolbar/voice
provider selection and permissions. Do not substitute “enabled” for “usable.”

Then prototype a visible native Talk action using Android's installed recognition
provider. Android exposes recognition intents and a recognizer API; availability,
permissions and lifecycle/error handling must be checked on this tablet. See the
[recognition intent reference](https://developer.android.com/reference/android/speech/RecognizerIntent)
and [recognizer reference](https://developer.android.com/reference/android/speech/SpeechRecognizer).
Prefer a bounded, user-started session. Stop on cancel/background/timeout and
handle no speech, missing service, denied permission and network failure.

Resolve transcript delivery before coding the full UI: no JavaScript/native
bridge or injected executable text. A narrow authenticated loopback handoff may
bind a one-time result to the paired session, active conversation and composer
revision. Reject late results after navigation; preserve existing typed text and
cursor intent. Do not send automatically or overwrite recovery state. This is a
design direction to prove, not an existing API or a relaxation of AGENTS.md.

Touch points: `src/App.tsx`, `src/Chat.tsx`, `src/style.css`,
`src/recovery-store.ts`, `src/use-recovery.ts`, `server/main.ts`, Android
`MainActivity.java`, manifest and origin/transfer policies as applicable.

Done when Adam can see and use Talk without hunting in a keyboard menu, dictate
the minister-meeting request, correct a name, send once, and dictate a follow-up
into the same chat. Cancel, rotation, app switching and recovery cannot lose text
or submit twice. A new user can explain where the report and its chat are saved.

### 2. Connect the discussion to OneDrive discovery and intake

Add narrowly typed tools for authorized account capability summaries, bounded
folder/file discovery and import. Reuse `server/onedrive.ts`, document validation
and source identity tracking instead of a second connection system. Rank likely
folders within the chosen role/account; show ambiguous matches rather than guess.
Bound results/pages, depth, bytes and time. Persist the chosen role destination
privately using identity/drive/folder IDs plus a readable breadcrumb.

Give Assistant/meeting workers access to the relevant supported document readers
and imports. Today their tool set differs from normal document workers. Verify
Word, Excel, PowerPoint and PDF material really reaches the meeting brief, rather
than only exposing new buttons. Keep extraction coverage warnings and existing
100,000-character limits visible until long-document reading is implemented.

Done when the request finds an authorized existing Council location and relevant
materials, asks only for a real ambiguity, creates one local assignment and can
cite its imported sources. An unavailable IT-restricted account never causes a
silent fallback into another account.

### 3. Complete reviewed filing from the conversation

Reuse report export and `publishNew` behind the inline destination review. Add
new-folder creation only as an explicit reviewed operation, with identity checks,
name validation, collision handling and a durable operation/receipt record.
Reassess `project-control.yaml` before introducing this new external write: its
current boundary covers user-selected new report exports, not arbitrary filing.
Do not expose broad move/delete/overwrite operations to accomplish this story.

Receipt state must distinguish local brief, created cloud folder, uploaded files,
partial completion and unknown outcome. Never repeat a timed-out create/upload
blindly. Verify the destination account and reopen the saved file; record the
actual resulting item identity/link and version where supplied by the service.

Done when an approved synthetic brief saves under the selected account and folder,
opens on Windows, and a collision, expired login, changed account or interrupted
upload produces an honest recoverable result without duplicate publication.

### 4. Prove the complete meeting story before more features

Use a synthetic meeting, mail and documents first. Run the whole story from the
Talk button through source gathering, two revisions, reviewed OneDrive filing,
and opening the result in Windows Office. Then conduct Adam's live test only in
his authorized accounts. Verify independently with no USB runtime forwarding.
Retain the Word/Excel/PowerPoint edit-save-reimport path already delivered.

Full agenda reading, Share intake, revision association and portable workspace
export remain in the earlier executive workflow plan. Prioritize this coherent
meeting story before adding more controls or expanding into autonomous work.

## Start here on Windows

Immediate intent: continue development and tablet testing from the other office.
Also preserve the product requirement to open filed work on Windows. Native
Windows server parity and cross-device conversation synchronization are unverified
and must not be described as already delivered.

1. Open the existing `ForgeOS-Device-Agent` checkout and check `git status`. Preserve
   local edits. With a clean compatible branch, run `git pull --ff-only`; if it
   cannot fast-forward, inspect rather than reset. If no checkout exists, clone
   `https://github.com/Adamgdwn/ForgeOS-Device-Agent.git`.
2. Work in `AI Centric Galaxy Tab S9`. Read this document, its `AGENTS.md`,
   `project-control.yaml`, and the September 22 runbook/verification record. The
   ForgeOS parent runtime is separate; do not run flashing or migration workflows.
3. Start with the already-installed 0.4.0 on the tablet. Authorize Windows USB
   debugging only if needed for development. Inspect the connected serial/model,
   runtime mode and active work before changing anything. Preserve Termux,
   `.local/`, Codex/Microsoft sessions, unsent drafts and existing work folders.
4. Inspect available tooling before installing anything. The known build path is
   Linux; use an existing suitable WSL environment if available. Windows/WSL has
   not been verified in this handoff. The Bash `galaxy` launcher is not PowerShell.
   Node 24.14+ and locked npm dependencies are required. `npm ci`, `npm run build`
   and `npm test` are the package commands; integration tests also require Python
   3, Poppler/pdftotext, Pandoc and the report-conversion dependencies in the runbook.
   POSIX process-group termination, `timeout`, and binary names need attention
   before claiming native Windows backend compatibility. Do not disable tests or
   the pinned Codex protocol check to make a Windows run appear to pass.
5. Android needs Java 17, SDK 36 and the tracked Gradle wrapper. `gradlew.bat` is
   present, but its Windows build has not been run here. Run equivalent assembly,
   unit-test and lint tasks for app/reader with one worker and a ten-minute bound.
   Before installation compare signing certificates: a different machine's debug
   key will not update the installed package. Obtain the existing signing material
   through an approved private channel if needed; never commit it or uninstall the
   working app to bypass a signature mismatch.
6. For an update, first take a consistent private DB/document backup and confirm
   no active worker or unsaved user work. Use `adb install -r` with the matching
   signer and the runbook's code-only transfer. Preserve `shared/` and
   `server/office-text.py`; never replace `.local/` or copy host-native binaries
   over Termux dependencies. Do not use `galaxy android-install`: it adds the
   legacy workstation USB reverse route. Daily tablet use stays independent.
7. Start implementation with item 1 (voice + entry clarity), then run the meeting
   acceptance story. Record the Windows environment and what actually passes.
   Git is the source handoff; private state transfer is a separate deliberate task.

Suggested prompt for the next coding session:

> Continue Galaxy Workspace from docs/2026-09-23 - Voice First Assistant and
> Windows Handoff.md. Preserve the independent tablet runtime and existing data.
> Start by reproducing the missing voice control, then implement visible Talk and
> conversation-first navigation. Keep the minister-meeting-to-OneDrive workflow
> as the acceptance story. Inspect Windows tooling and app signing before updates.

## Original handoff verification and scope

The original ten-minute handoff changed documentation only. At that point the
application remained 0.4.0 and voice, conversational OneDrive filing and Windows
parity were not built. Baseline verification records 64 app tests, eight
Android tests, builds/lint and actual tablet Office/recovery checks in the
[September 22 verification record](2026-09-22%20-%20Verification.md).

Original handoff checks on September 23: governance preflight passed (246 tests,
one skipped, two subtests); all 64 Galaxy tests passed; TypeScript/Vite build
passed and produced the unchanged `index-CGukaKgj.js` bundle; all eight local
Markdown links in this document and README resolve. No Android source changed,
so the prior Android build/device verification was not represented as a new run.
The bounded preflight, build and test processes all completed; no background
test or build job was left running.

The September 23 check reads keyboard/provider configuration without changing it.
No audio was recorded, account grants changed, cloud documents written or runtime
processes stopped. Parent and subproject governance manifests have no exceptions.
The unrelated parent README migration edits and September 5 Portfolio Status
remain preserved outside the Galaxy handoff commit; that older archival marker
is not an instruction to archive this active subproject.

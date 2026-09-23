# Voice-first Assistant and Windows handoff

Last Updated: 2026-09-23
Status: implementation plan and development handoff; these changes are not yet installed
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

## Handoff verification and scope

This handoff changes documentation only. The application remains 0.4.0; there is
no claim that voice, conversational OneDrive filing or Windows parity was built
in the ten-minute handoff. Baseline verification records 64 app tests, eight
Android tests, builds/lint and actual tablet Office/recovery checks in the
[September 22 verification record](2026-09-22%20-%20Verification.md).

Fresh handoff checks on September 23: governance preflight passed (246 tests,
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

# Galaxy Workspace executive workflow plan

Last Updated: 2026-09-22

Status: 0.4.0 delivers the continuity and core Office handoff increments below. The remaining roadmap is still planned.

## Delivered in 0.4.0

Unsent chat/attachments and unfinished report edits now have acknowledged SQLite recovery, browser fallback and per-conversation isolation. Report edits preserve their base hash/path and reject stale saves. Engine startup failures stay distinct from pairing; the native launcher can re-pair locally without terminal codes.

Workspace originals and exports support native Open, Save a copy and Share a copy. Confirmed saves offer Open/Share and a Last saved file launcher entry. Files show friendly names and grouped extraction details. Durable export history retains earlier versions and destination receipts. XLSX/PPTX can be imported, read by typed document tools and opened in the installed Office apps; extracted views label formula/cache and visual-content limits.

Not delivered: complete long-PDF/page coverage, OCR, Office revision association, automatic Office writeback, Android Share intake, recent/pinned folders, destination defaults, archive controls, portable workspaces and user-facing backup/restore. Office revisions currently return through Add material. Formatted spreadsheets/decks are edited or created in the existing Office apps.

The original assessment below is retained as the roadmap; the delivered-status section above supersedes its earlier gap statements.

## Product outcome

Adam should be able to prepare for a meeting, find a fact during discussion,
combine correspondence and documents, revise a report, and leave with a saved
document he can find on Windows. The tablet runs independently. Windows, Linux
and eventually Mac remain the places for heavier work.

Galaxy owns gathering, source-aware discussion, drafting and continuity. Word,
Excel and PowerPoint own Office layout, calculations, presentations and editing; OneDrive owns cloud filing and sharing; Outlook
owns email and calendar actions; Samsung My Files owns ordinary device-file
management. Use the installed PDF and note applications where they help.

Keep the existing Assistant, workspaces, Files, Report, Connections and System
layout. Add contextual actions and useful defaults instead of another dashboard.
Do not add a terminal, Office clone, new document-management subscription or
second task-management system to complete these workflows.

## What this assessment checked

Reviewed the current React, Node, Android launcher and storage implementation at
`67dcd76`, the September 22 live verification, and the connected tablet's package
inventory and document intent handlers. Word, Excel, PowerPoint, Outlook,
OneDrive, Samsung My Files, Xodo, Samsung Notes, OneNote and Planner are installed.
Android advertises Word as a DOCX handler and several PDF handlers, including
Xodo. This establishes availability, not successful editing, licensing or saving.

The earlier live check imported two Word documents and a roughly 14 MB agenda,
opened their text previews, and had Codex read the available text. It did not
read the entire agenda. This assessment launched no Office apps, changed no
accounts, moved no user files and made no cloud writes. Private device evidence
and the previously observed folder trail remain in ignored
`.local/verification/2026-09-22/workflow-audit/`.

Microsoft's mobile editing rules depend on the subscription and screen size.
Confirm the existing account's editing entitlement on this large tablet before
counting Word editing as complete; installation alone is insufficient. Galaxy's
text report editor and exports remain the available fallback. See
[Microsoft's mobile licensing guidance](https://support.microsoft.com/en-us/microsoft-365-activation-licensing/mobile/what-you-can-do-in-the-microsoft-365-apps-on-mobile-devices-with-a-microsoft-365-subscription).

## Step-by-step coverage

“Available” means implemented, with evidence qualified where necessary. “Manual”
means an existing application can supply the step, but Galaxy does not yet join
it into a seamless flow. Proposed controls below are requirements, not current
button labels.

| User's step | Available route today | Gap and required completion |
| --- | --- | --- |
| Open the tablet and resume | Native launcher starts the local engine; saved conversations persist | Recover unsent chat and unsaved report text; distinguish engine startup failure from expired pairing; remove terminal steps from routine local pairing recovery |
| Find the right meeting | Assistant reads the visible Outlook calendar and relevant mail | Show the specific account, meeting date/time and observed coverage; never label a partial calendar read complete |
| Find a document quickly | Browse OneDrive folders; System searches shared-storage filenames | Recent/pinned workspaces and folder shortcuts first; bounded filename search within a chosen connected account/folder next |
| Gather across folders and accounts | Add material supports OneDrive selection, Android files, pasted mail and `.eml` | Accept Android Share into a chosen workspace; retain source identity, received date and duplicate/version distinction |
| Open a document | Text previews; imported cloud files have Open original links | One obvious Open in app action for local originals and exported copies; web links do not guarantee Word will open |
| Download a document | Prepared reports use Android's save picker; originals can be saved in OneDrive | Download original from Galaxy, retain the resulting location, offer Open and Share after saving |
| Read a whole agenda | Word/PDF text extraction, bounded and labelled | Page/section reading and a coverage record beyond the 100,000-character cap; detect empty/scanned or inaccessible sections |
| Ask a quick question | Quick answers, Brief me, follow-up chat and source links | Cite accessible page/section references and state missing evidence before consequential conclusions |
| Make a small report correction | Edit text beside chat; explicit save; content-hash conflict checks | Durable recovery of unsaved edits and a clear saved/unsaved indicator |
| Edit Office formatting or a source document | Manually open the file in Word/Excel/PowerPoint | Preserve the original, open a working copy when intended, record where it was saved, explicitly bring the revision back |
| Mark up a PDF or take pen notes | Installed PDF/note apps are available separately | Open/export/import handoff; identify whether annotations or handwriting are readable by Galaxy before summarizing them |
| Consolidate a summary report | Isolated report draft; conversation refinement; DOCX/PDF/Markdown export | Friendly document names, clear current working version and durable export history; linked source evidence must travel sensibly with the output |
| Save in the right folder | Explicit account/folder picker for new OneDrive report exports | Remember a chosen destination per workspace; show account, breadcrumb, version and verified result; live cloud publication still needs testing |
| Organize documents | OneDrive and My Files provide ordinary filing | Pin existing folders, show file origin/current copy, archive workspace without deleting sources; use native apps for moves/renames |
| Share or send the finished result | Manually attach a downloaded file in Outlook or share through OneDrive | Android Sharesheet from the saved output; user chooses recipients and sends in the destination app |
| Record decisions and follow-ups | Ask for a decision/action table in the report | Simple meeting-notes section; preserve named owners and dates; manual handoff to Outlook/Planner, without implying tasks were created |
| Work without a network | Imported files and saved work are local; AI and cloud access need internet | Offline readiness view and exported meeting pack; test airplane-mode cold start and reopening actual originals |
| Continue on Windows | Exported files can move through OneDrive or normal file transfer | A portable workspace package for sources, report, evidence and readable conversation; no live two-way database sync |
| Recover from loss or replacement | Developer runbook describes protected state backup | User-facing export/restore, verified restoration and clear coverage of what is backed up |

## Six everyday workflows

### 1. Prepare for Council or an operations meeting

1. Ask Assistant to identify the event and relevant correspondence. Confirm the
   returned event belongs to the intended calendar and date.
2. Save a named meeting workspace. Add the agenda, background papers and selected
   correspondence from their existing locations.
3. Read the source coverage: available documents, missing attachments, scanned
   pages and stale imports. A cached event is not proof of current synchronization.
4. Request a short brief: purpose, known facts, decisions needed, questions,
   unresolved issues and source references. Label suggested positions as proposals.
5. Save the brief and export a PDF for quick reading. Open the saved copy before
   leaving. Keep the full agenda accessible in the PDF app as well.

Completion: one identifiable meeting workspace, a readable saved brief, the
actual full agenda, and explicit missing-source information. Today's visible
Outlook reading and truncated PDF text do not establish complete coverage.

### 2. Find an answer during the meeting

1. Reopen the current meeting from Recent or a pin (planned); today select its
   workspace in the sidebar.
2. Ask a short question, for example “What changed since the earlier briefing?”
   Scope the question to the attached documents and their versions.
3. Open the cited passage and, when layout or a table matters, open the original
   in Word or the PDF app.
4. Dictate or type a note, decision or question. Save it locally; no network
   should be required merely to retain the note.

Completion: an answer with checkable evidence, or a clear statement that the
needed page/source is unavailable. Do not invent an answer from a partial pack.

### 3. Consolidate emails and documents into a report

1. Create/open the assignment's workspace. Select material from multiple folders
   and only the accounts relevant to this assignment.
2. Add email text with sender, subject and date, or import saved `.eml` with
   supported attachments. Until Share intake exists, save attachments from
   Outlook to a chosen device folder and use Add material.
3. Ask for a source inventory, conflicts and missing information before drafting.
   Similar filenames must not silently collapse into one document.
4. Draft and refine the report. Make direct text corrections when faster than
   asking. Preserve citations and separate facts from recommendations.
5. Save, export and reopen the output. Check important numbers/tables against
   the originals, then file it in the selected existing destination.

Completion: sources remain intact, the report is saved, and the output's account,
folder and version are known. A chat answer alone does not count as a saved report.

### 4. Make a quick change in Word and return to Galaxy

1. Decide whether this is an edit to the original cloud document or a separate
   working copy. Default to a copy for a new assessment/report.
2. Open the actual DOCX in Word. Confirm the app can edit under its signed-in
   account. Use Word for formatting, tables and document comments.
3. Save to an explicitly chosen local or OneDrive location and confirm the save
   there. Switching back to Galaxy is not evidence that Word saved.
4. Re-import the revised file with Add material today. The planned **Bring back
   revision** action associates it with the prior version and shows what changed.
5. Ask Galaxy to assess that revision. It must not continue using the old snapshot
   without telling the user.

The Word copy and Galaxy's Markdown report are separate documents. Re-importing
a DOCX does not update the report editor or preserve Word layout in AI edits.
For further AI revisions, discuss proposed changes or explicitly start a new
report revision; never silently regenerate and replace the formatted DOCX.

### 5. Close the meeting and share the result

1. Record decisions, outstanding questions, action owners and due dates. Leave
   unknown owners/dates blank instead of guessing.
2. Prepare the final report or follow-up email text, review it and save it.
3. Export Word for collaborative editing or PDF for a stable reading copy.
4. File it in the assignment's chosen folder. Use Outlook or OneDrive to address
   and send/share it. Galaxy should offer the handoff, then distinguish “opened
   sharing” from “sent”; only the destination app knows the latter.
5. Add reminders/events/tasks manually in the existing app when needed. Keep the
   action list in the workspace and archive the workspace when finished (planned).

Completion: a saved deliverable, an explicit user-controlled communication step
and a recoverable action list. No automatic send or invitation responses.

### 6. Continue on Windows, then return to the tablet

1. Save the deliverable to the correct OneDrive account or transfer its downloaded
   copy. Verify that Windows opens that same saved file.
2. Make the desktop changes and let the chosen file location finish saving.
3. Re-import the changed document on the tablet. Show that it supersedes a prior
   source version; preserve both when changes need comparison.
4. For an entire assignment, use the planned portable workspace package. Include
   a readable conversation and source manifest, rather than relying on a live
   internal Codex session being transferable.

Git push distributes source code and these instructions. It does not transfer
the tablet's private documents, reports, conversations or account sign-ins.
Windows USB deployment/testing is a separate developer path; daily tablet use
continues without a connected computer.

For the Windows testing handoff, pull the current repository and read this plan,
the user guide and the standalone section of the runbook first. Inspect the
installed tablet before updating it; preserve Termux's private state and tablet
Codex login. Do not copy workstation credentials over them or use the legacy
`android-install` flow that adds a USB runtime route. Record the tested app/code
version and finish the acceptance run with the cable disconnected. Windows build
tooling itself has not been verified by this assessment.

## Folder and document ownership

Respect existing OneDrive trees. Start with shortcuts to verified existing
folders, not a new universal filing tree or a bulk move. The previously visited
audit-meeting folder is useful navigation evidence, but it does not establish
the intended root for every Council assignment. Keep actual account/folder IDs
in private settings, never in a public handoff or guessed from labels.

| Workspace context | Destination rule |
| --- | --- |
| Council | Select the authorized Council destination explicitly once; the unused campaign account is excluded. Do not infer Council storage from a Personal card label. |
| Operations | Bind a user-selected existing business folder only when that account is authorized; an unavailable/IT-restricted connection is not a writable destination. |
| Personal / other work | Use the selected account's actual identity and folder, keeping unrelated material separate by default. |
| System | Permanent tablet workspace; no business-document filing role. |

A proposed shortcut stores a friendly label plus immutable account identity,
drive ID and folder ID. Reconnection to another account invalidates it. Never
fall back silently to a different account or cloud root. Remember the chosen
destination; require another choice only when it is missing, changed or unavailable.

When a new assignment folder is useful, propose a dated name such as
`YYYY-MM-DD - Meeting or assignment` inside the chosen existing parent. Reuse an
existing meeting folder where appropriate. Start with one folder, adding Sources
or Final subfolders only if needed. Cloud folder creation is not yet exposed in
Galaxy; OneDrive can handle it today.

Each visible document should explain which object it is: **original**, **imported
snapshot**, **working copy**, or **exported report**. Keep technical import IDs
and extracted-text sidecars behind document details; show the original friendly
name in the normal list. Show the source account, import time, source version,
current save location and full/partial text coverage there.

## Implementation order and finish criteria

These are bounded increments. Complete the first two before optional enhancements.

### A. Protect continuity and make saving understandable

- Persist unsent chat and unsaved editor text per conversation. Restore after
  navigation/reload/process loss; retain the starting content hash so recovery
  cannot overwrite a newer saved report. Do not auto-send recovered text.
- Show saved/unsaved state and a durable output record: filename, format, report
  version, destination and success/uncertain outcome. A prepared export is not
  yet a downloaded or cloud-saved file.
- Fix the cold-start session check so a temporary engine error does not become
  a false pairing instruction. Provide a native, local recovery action for
  expired pairing without exposing credentials to other apps or the model.
- Present friendly source names, group extraction artifacts with their originals,
  and make source/working/exported versions visibly distinct.

Touch points: `src/App.tsx`, `src/Chat.tsx`, `src/Report.tsx`, `server/store.ts`,
`server/main.ts`, native launcher. No schema change should discard saved work.

Finish: interrupt editing, switch workspaces, restart and reconnect; the text
returns once, the latest saved version is protected, and the user can locate a
previous output without exporting again.

### B. Complete the document round trip and whole-document access

- One document menu: Preview, Open in app, Save a copy, Use in conversation and
  Details. Report outputs additionally offer Share. Avoid a permanently expanded
  row of buttons.
- Download exact original bytes as well as report exports. Offer native Open and
  Share after Android confirms the selected destination was written successfully.
- Add explicit revision import. First implementation can reuse the picker and
  source-import pipeline; automatic file watching is unnecessary.
- Add bounded PDF page ranges and Word section/text ranges with stable document
  hashes and coverage metadata. Reading the first preview must never imply the
  entire document was assessed. Track unread pages/sections and extraction errors.
- Detect image-only/scanned content and unsupported inputs visibly. Keep OCR as a
  separate, measured increment; offer the original and explicit manual text input
  instead of pretending an unreadable document is empty or fully assessed.

Touch points: `server/files.ts`, `server/onedrive.ts`, `server/workspace-tools.ts`,
Assistant's equivalent tools, `server/materials.ts`, `server/main.ts`, previews,
native transfer policy and launcher. Align actual stream/import/preview limits;
do not solve whole-document access by raising one character limit without bounds.

Finish: choose a DOCX, open a copy in Word, edit/save/re-import, and demonstrate
that Galaxy reads the change while the original is unchanged. For a long PDF,
answer from a known passage beyond the old cutoff and show its page reference.
An image-only page remains explicitly unassessed unless OCR actually succeeds.

### C. Shorten gathering and filing

- Accept text and supported attachments via Android Share; choose new/existing
  workspace once, preview the intake, then reuse normal import validation.
- Add Recent and a small number of pinned workspaces/folders. Add scoped filename
  search, visible account identity, duplicate detection and explicit refresh to a
  new source version. Start with filenames, not a mailbox-wide semantic index.
- Remember output destinations and offer OneDrive/My Files for broader filing.
  Support workspace rename/archive without deleting source documents.
- Add a compact notes/decisions/actions section using existing report storage.
  Use installed note apps for handwriting, with deliberate import when needed.

Finish: start with an Outlook attachment and a document elsewhere, consolidate
them in the intended workspace, save a result to its remembered folder, then find
and reopen it without reconstructing the folder path.

### D. Make the assignment portable and recoverable

- Provide an offline readiness check and a local meeting pack containing the
  latest saved brief and selected originals. No offline AI promise.
- Provide a versioned workspace export/restore: sources, saved report versions,
  notes, readable conversation and provenance. Exclude login tokens, keys and
  session cookies; restoring requires normal sign-in again.
- Retain relative paths, hashes and explicit unsupported/missing items. Restore
  into a new workspace, validate archive paths and sizes, and never merge an
  active SQLite database from two machines.
- Keep private backups under user-chosen access controls; exporting business
  material to shared storage is an explicit user action with a named destination.

Finish: reopen the local pack in airplane mode, restore an exported workspace
into clean test state, and verify that Windows can open the deliverables and
source manifest. Do not claim conversation/session synchronization.

## Native integration approach

Extend the existing file picker and transfer policy. Android's document picker
supplies user-selected content URIs for opening and saving; a successful save
needs its own receipt. Save-as creates a new document rather than silently
overwriting an existing one. See
[Android's storage framework](https://developer.android.com/training/data-storage/shared/documents-files).

For app handoff, use a narrowly scoped content URI and temporary permission,
with the correct MIME type and a system chooser. Use only private transfer files
intended for that action, not the whole runtime directory. Keep source viewing
read-only; external editing uses an explicitly created copy. See
[Android's file-sharing guidance](https://developer.android.com/training/secure-file-sharing/share-file).

Initiate these actions from explicit user taps through narrowly validated native
routes. Retain the prohibition on a JavaScript/native bridge and arbitrary
model-directed app launches. Add an Android Share receiver only for bounded,
validated text/files and a visible destination-selection flow. Cancellation,
missing handlers, revoked URI permission and app process death need recoverable
states. Temporary transfer permissions are not a credential-sharing mechanism.

## Acceptance run for the next build

Use synthetic documents and a clearly named test folder. Delete only generated
test artifacts after recording results. Do not send a real message or modify a
business original to prove a handoff. Each row needs an actual receipt or observed
result, not a model statement or package-install check.

| Scenario | Evidence required |
| --- | --- |
| Cold launch, delayed engine, expired pairing | Saved context preserved; truthful recovery screen; routine recovery needs no terminal |
| Type, navigate, rotate, background, process restart | Unsent chat and unsaved report recovered; no duplicate send; concurrent saved changes protected |
| Word round trip | Original hash unchanged; revised file saved at known location; re-imported text contains the edit; current Word entitlement confirmed |
| Source/report download | Exact bytes/expected format; saved location; reopened file; cancelled save never reports success |
| Native sharing | Correct file/filename/format in destination composer; no automatic send; cancel returns safely |
| Long, scanned, protected and unsupported documents | Late-page evidence works; partial/unreadable inputs labelled; boundaries and parser timeouts enforced |
| Mixed-source meeting collection | Correct account/source labels, duplicates/version handling, source links and missing attachments visible |
| Cloud save and conflict | Intended account/folder receipt, reopen successful, existing file not overwritten; uncertain result not blindly retried |
| Reopen old export after editing report | Old output remains identifiable; current versus exported version is obvious |
| Wrong/disconnected account or restricted folder | Draft retained; helpful destination choice; no silent account fallback |
| Offline and network switching | Saved material opens without network; AI unavailability clear; resuming does not resubmit a request |
| Windows handoff and restore | Same deliverable opens; changed revision re-imports; clean-state restore contains expected sources/report/history and no secrets |
| Tablet ergonomics | Landscape/portrait, split-screen with Word/Outlook, keyboard, dictation and S Pen tested on the actual tablet |

## Existing-app fallbacks while this is built

Use OneDrive to save an original to a selected device folder, then My Files to
find/open it. Microsoft's documented Android flow uses the file's More menu and
Save. See [OneDrive downloads](https://support.microsoft.com/en-us/onedrive/how-to-download-onedrive-files-to-your-mobile).

Use OneDrive's own sharing controls for links/permissions or file attachments,
then finish in the chosen app. This is separate from Galaxy's local save. See
[OneDrive sharing](https://support.microsoft.com/en-us/onedrive/share-files-in-onedrive-for-android).

For offline use, download and open the actual needed documents before leaving.
OneDrive's offline designation and Word's offline-editing behavior are different
paths; do not assume an offline-marked file is a synchronized editable working
copy. Verify saving and reconnection for the chosen app. See
[OneDrive offline access](https://support.microsoft.com/en-us/onedrive/read-files-or-folders-offline-in-onedrive-for-android)
and [Word offline work](https://support.microsoft.com/en-US/Word/can-i-work-offline).

## Scope of this planning pass

The workflow plan and user guidance are the deliverables of this pass. No runtime
feature or APK was changed. Earlier live tests remain evidence for the existing
build, not for the proposed integrations. Start implementation with increment A,
then B; C and D follow without expanding into a full Office or email client.

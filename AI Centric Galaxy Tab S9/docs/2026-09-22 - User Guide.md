# Galaxy Workspace user guide

Last Updated: 2026-09-22

## Open and use it

Open **Galaxy Workspace → Open workspace**. The launcher starts the engine on this tablet. Look for **Running on this tablet** and **On-device tools connected**. No laptop, USB cable or Tailscale is needed. Internet is needed for Codex replies, cloud documents and current Outlook synchronization. Saved work stays on the tablet.

Keep **Termux** installed and its engine notification running while using Galaxy. Keep **Galaxy Device Tools** enabled in **Android Settings → Accessibility → Installed apps**. Termux holds your saved work and Codex sign-in; uninstalling it removes that data.

## Prepare for a meeting

Open **Assistant** and ask something like:

> Check my calendar for tomorrow. Find the meeting with the minister and relevant emails. Save a meeting brief with the facts, questions and decisions I should prepare for.

Galaxy brings Outlook forward to read its visible calendar and mail, then returns to your conversation. Keep the tablet unlocked and let it finish before navigating Outlook yourself. It can read and search; it cannot send email, accept invitations or edit events. Opening a message can mark it read.

If it cannot identify the meeting or an account needs sign-in, it should say so. Current calendar access is separate from OneDrive access. The September 22 warning for **connect@adamgoodwin.ca** concerned your unused campaign account, not your Council account. You do not need to sign in to that account to use Galaxy. Ask for the relevant Council calendar and emails, and check that the returned sources match the meeting.

A saved brief appears as a named workspace. Reopen it and say “Make the opening shorter,” “What are we missing?” or “Add these documents to our assessment.” The brief and its dated source snapshots live on this tablet. Cloud export is a separate action.

## Gather documents and build a report

1. Tap **+** beside **Your workspaces** to name an assignment, or open an existing workspace and choose **Add material**.
2. Choose **OneDrive files**, **files on this device**, or **Paste an email**. Select documents from the folders/accounts you need. Subject, sender and date help identify pasted correspondence.
3. Ask for an assessment: “Summarize the issues, compare the numbers, and flag gaps before we write the report.” Tap source links to check the original material.
4. Use **Draft report**, or choose **Full conversation** and ask to create a report. Galaxy saves an isolated draft. Continue discussing improvements, or edit directly beside chat and tap **Save draft text**.
5. Use **Export a copy** for Word, PDF or Markdown, then **Prepare export → Open / save / share copy**. Choose **Open in app**, **Save a copy**, or **Share a copy**. Android's save picker chooses the destination. OneDrive upload remains a separate, explicit action.

**Quick answers** keeps responses brief and document tools read-only. **Brief me** requests a short assessment. **Explain further** expands an answer. **Add to report** appends an answer in the editor for you to review and save.

Imports are snapshots, not continuous synchronization. Re-import if originals change. A batch supports up to 50 source files: DOCX, XLSX, PPTX and PDF up to 20 MB each, other supported files up to 8 MB each, and 25 MB total. Plain text, Markdown, CSV/TSV, JSON and saved `.eml` messages are also supported. Convert old `.doc`, `.xls` or `.ppt` files to modern formats first; `.msg`, macros and OCR are not supported.

## Word, Excel, PowerPoint and PDFs

1. In a workspace, open **Files** and tap the document. Friendly names identify the original; **Document details** contains its workspace path and extracted-text copy.
2. Choose **Open / save a copy**. **Open in app** shows Android's app chooser: use Word for DOCX, Excel for XLSX, PowerPoint for PPTX or your PDF app. **Save a copy** stores the exact original bytes wherever you choose. **Share a copy** opens Android's Sharesheet.
3. For edits, use the Office app's **Save a copy/Save As** into a known local or OneDrive folder. Galaxy hands out a separate, read-only source copy; Office changes must be saved separately. Editing availability depends on the signed-in account's [Microsoft 365 entitlement](https://support.microsoft.com/en-us/microsoft-365-activation-licensing/mobile/what-you-can-do-in-the-microsoft-365-apps-on-mobile-devices-with-a-microsoft-365-subscription).
4. Return to Galaxy → **Add material → Files on this device** (or OneDrive) and select the revised file. Tell the conversation which version to use. Re-importing is explicit; changes in Office do not silently update Galaxy's earlier snapshot.

After **Save a copy**, the confirmation offers **Open** and **Share**. The launcher remembers **Last saved file** for reopening later. This records the chosen provider's filename; it is not proof that a cloud provider has finished synchronizing. If a grant expires or the file moves, select the file again through My Files or OneDrive.

Excel previews identify sheets and cell addresses, including hidden sheets. They show stored values and formula text; cached formula results can be absent or stale. Dates/currency may appear as raw numbers. Open Excel to calculate and check charts, formatting, external data or important totals.

PowerPoint previews identify slides and extract text, tables and speaker notes. They do not interpret pictures, charts, animations or layout. Open PowerPoint to inspect or present the actual deck. All extracted previews are limited to 100,000 characters and visibly flag truncation. Scanned PDFs and image-only slides require the original app; Galaxy does not perform OCR.

For a Galaxy report, **Save draft text**, choose an export format and **Prepare export**. **Previous exports** reopens older prepared versions even after restarting; it shows the creation time and any confirmed device/OneDrive save. Preparing an export does not itself publish it. A pending or uncertain OneDrive upload must be checked at its destination before trying a new export.

An exported Word document and Galaxy's report draft are separate copies. Bringing a revised DOCX back adds a source document; it does not replace the report editor. Ask for proposed changes or a new report revision explicitly. Galaxy's text editor does not preserve Office layout. Galaxy currently generates DOCX/PDF/Markdown reports; creating formatted XLSX workbooks and PPTX decks is still done in the Office apps.

## File, share and continue on Windows

Use OneDrive for cloud folders and My Files for device folders. Keep using your existing filing structure. Galaxy does not currently provide folder bookmarks, cloud filename search, moving/renaming originals or automatic folder synchronization.

To send a finished report, choose **Share a copy**, then Outlook or another destination app; alternatively use OneDrive sharing. Choose the sender account, recipients and permissions there, then send from that app. Galaxy does not send mail or create follow-up calendar events/tasks.

For Windows, save the finished file into the intended OneDrive account/folder, or transfer the downloaded copy normally. Open it on Windows to confirm it arrived. After further edits, re-import the new version on the tablet. Galaxy's conversations and private workspaces do not synchronize to Windows, and pushing the app's Git repository does not back them up.

Unsent chat, selected attachments, answer style and unfinished report text recover per conversation. Wait for **recovery saved** before closing the app. Recovery keeps unfinished work; **Save draft text** still publishes your edits into the workspace report. **Finish later** keeps the editor copy, **Resume edits** returns to it, and **Discard edits** asks before removing it. A warning means recovery is unconfirmed: keep the screen open and save/copy important text. If the saved report changed meanwhile, Galaxy preserves your edits and blocks overwriting it until you compare the latest version.

An interrupted send is never repeated automatically. Use **Check previous send** to look up its recorded status; this does not submit another AI request.

Before going offline, save and open the brief and originals you need. Local documents and recovery stay on the tablet; AI replies need internet. A full meeting in airplane mode remains a field test. The [executive workflow plan](2026-09-22%20-%20Executive%20Workflow%20Plan.md) separates delivered features from later work, including full agenda reading and portable workspaces.

## Connections and folders

Open **Connections → Browse files** and open a folder. **Tap a document's name to read its text**. Choose **Select for workspace** in the preview, or use the checkboxes beside filenames to select several documents. Name the collection and tap **Open as a workspace**; when adding to existing work, tap **Add to workspace**. In the workspace, open **Files**, tap a document, and choose **Use in conversation** to discuss it. Office/PDF previews show extracted text; **Open original** visits the cloud document, while a workspace preview’s **Open / save a copy** hands the imported snapshot to Android. Long previews are labelled when shortened.

The Personal and linked Guided AI Labs connections both passed live browsing on the tablet. The linked CLI account supports reading/importing and local drafts; it cannot save back to OneDrive in this pilot.

Each independent account uses **Sign in with Microsoft**, a one-time code and Microsoft's normal sign-in page. You do not need an application ID. Check the displayed email, since a card's label can differ from the signed-in account. **Remove** removes the connection from Galaxy and preserves your OneDrive files and imported work. **Add OneDrive account** restores an available slot. Organizational approval can still be required.

For tablet folders, use **System → Tablet files** to browse/preview shared storage, or use the Android file picker to bring selected files into a document workspace. Hidden files, private app storage and Android system directories are excluded.

## Check or improve the tablet

Open **System**. Ask “How is my storage looking?” or “Find the budget PDF in Download.” Facts come from the tablet's current battery, storage, memory, software and settings. File search matches names, up to six levels and 100 results; a smaller folder helps.

For an improvement, try “Keep the screen on for ten minutes while I read meeting notes.” Galaxy shows the old value, new value and reason. Review **Apply change** or **Leave as is**. **Undo change** restores the prior value if nothing else has changed it. An uncertain result is never retried automatically.

Supported settings: screen timeout, automatic brightness, auto-rotate, and displaying the on-screen keyboard alongside a physical keyboard. System does not delete files, uninstall apps, clear app data, root or flash the device.

## Dictate

Tap the message box, open the keyboard and use its microphone (bottom left on the checked Samsung keyboard). Dictate, review the text and tap Send. Samsung Keyboard and Google voice typing are already enabled; no separate dictation app was installed. Galaxy does not record audio itself. Actual spoken recognition accuracy remains your field test.

## Reopen or recover

After a tablet restart, unlock it and open Galaxy. If needed, choose **Connection → Use this tablet**, wait a few seconds, then **Check connection**. If Android stopped Termux, open Termux once and return to Galaxy. A missing device connection usually means Galaxy Device Tools needs re-enabling in Accessibility settings.

If local pairing expires after seven days, use the native **Home → Connection → Reconnect this tablet** button. It reconnects to this tablet's engine without copying a code or opening a terminal. This is separate from Microsoft and Codex account sign-in. A slow/unavailable engine shows a retry state rather than pretending your pairing expired. Saved conversations, unfinished text and reports remain; reconnecting never resubmits an AI message.

The transfer preserved existing history and documents but started fresh internal Codex threads. In an older conversation, mention the report or topic again if the follow-up needs earlier context. New conversations retain their normal thread continuity.

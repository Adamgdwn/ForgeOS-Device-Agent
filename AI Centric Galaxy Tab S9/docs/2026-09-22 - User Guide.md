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
5. Use **Export a copy** for Word, PDF or Markdown. Android's save picker chooses where to put a downloaded copy. Choose a OneDrive destination explicitly when uploading.

**Quick answers** keeps responses brief and document tools read-only. **Brief me** requests a short assessment. **Explain further** expands an answer. **Add to report** appends an answer in the editor for you to review and save.

Imports are snapshots, not continuous synchronization. Re-import if cloud originals change. A batch supports up to 50 source files: Word/PDF up to 20 MB each, other files up to 8 MB each, and 25 MB total. Word/PDF text, plain text, Markdown, CSV/TSV, JSON and saved `.eml` messages are supported; OCR, `.msg` and full spreadsheet editing are not.

## Work with Word, PDFs and the file manager

Word, Excel, PowerPoint, OneDrive, Outlook, Samsung My Files and Xodo are already installed. Galaxy's preview is for reading extracted text. Use the existing document apps for formatting, spreadsheet work and PDF layout. Their editing/sign-in state has not been verified by this workflow review. Word editing on a large tablet depends on the signed-in account's [Microsoft 365 entitlement](https://support.microsoft.com/en-us/microsoft-365-activation-licensing/mobile/what-you-can-do-in-the-microsoft-365-apps-on-mobile-devices-with-a-microsoft-365-subscription).

For an existing OneDrive document:

1. Use **Open original**, or find the same account and file in the OneDrive app. The link may open a browser; it does not guarantee Word will launch.
2. To keep a device copy, use OneDrive's file menu **More → Save** and choose a folder. Find it in **My Files** and open it with Word or your PDF app. This is Microsoft's documented [download flow](https://support.microsoft.com/en-us/onedrive/how-to-download-onedrive-files-to-your-mobile); app wording or organizational restrictions may differ.
3. If making a separate assessment, save a working copy before changing the original. Finish the edit and confirm where the document was saved.
4. Back in Galaxy, use **Add material** to import the revised file. Say which version to use. Galaxy does not automatically receive changes made in Word or OneDrive.

For a Galaxy report, first **Save draft text**, then **Export a copy → Word → Prepare export → Download to this device**. Choose a memorable destination in Android's save picker, then open the file through My Files. Galaxy currently shows a save notification; it has no direct **Open in Word** or **Share** button after download.

The exported Word document and Galaxy's report draft are separate copies. Bringing a revised DOCX back adds a source document; it does not replace the text in the report editor. Ask for proposed changes or a new report revision explicitly. Word formatting is not preserved by Galaxy's text editor.

## File, share and continue on Windows

Use OneDrive for cloud folders and My Files for device folders. Keep using your existing filing structure. Galaxy does not currently provide folder bookmarks, cloud filename search, moving/renaming originals or automatic folder synchronization.

To send a finished report, download it and attach it in Outlook, or use the OneDrive app's sharing controls. Choose the sender account, recipients and permissions there, then send from that app. Galaxy does not send mail or create follow-up calendar events/tasks.

For Windows, save the finished file into the intended OneDrive account/folder, or transfer the downloaded copy normally. Open it on Windows to confirm it arrived. After further edits, re-import the new version on the tablet. Galaxy's conversations and private workspaces do not synchronize to Windows, and pushing the app's Git repository does not back them up.

Before changing conversations or closing the app, save report edits and copy any important unsent text elsewhere: automatic recovery of unsaved text is not implemented. Before going offline, export and open the brief and original documents you need. Local saved work remains on the tablet, but offline cold-start and a full meeting without network are still acceptance tests; AI replies need internet. A long or scanned agenda may not be fully readable by Galaxy even when its original opens in a PDF app.

The [executive workflow plan](2026-09-22%20-%20Executive%20Workflow%20Plan.md) records the gaps and the intended app handoffs. Its proposed buttons and features are not installed yet.

## Connections and folders

Open **Connections → Browse files** and open a folder. **Tap a document's name to read its text**. Choose **Select for workspace** in the preview, or use the checkboxes beside filenames to select several documents. Name the collection and tap **Open as a workspace**; when adding to existing work, tap **Add to workspace**. In the workspace, open **Files**, tap a document, and choose **Use in conversation** to discuss it. Word/PDF previews show extracted text; use **Open original** for the original document. Long previews are labelled when shortened.

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

If pairing expires after seven days, open Termux and run:

```sh
cd ~/galaxy-workspace
node scripts/pair.ts
```

Enter that code in Galaxy. This local pairing is separate from your Codex sign-in. Saved conversations and reports persist; reconnecting never resubmits a message automatically.

The transfer preserved existing history and documents but started fresh internal Codex threads. In an older conversation, mention the report or topic again if the follow-up needs earlier context. New conversations retain their normal thread continuity.

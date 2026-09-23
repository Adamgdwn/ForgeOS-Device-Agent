# Galaxy Workspace Android app

Last Updated: 2026-09-22

## Current deployment

Galaxy Workspace `com.adamgoodwin.galaxyworkspace`, version **0.4.0**, supplies the native launcher, icon, home screen, connection controls, toolbar and system file pickers. The React conversation/report UI remains embedded in Android WebView. Minimum Android 13; compile/target Android 16. This is a hybrid app and locally installed development build, not a Play Store release.

**Use this tablet** selects the local runtime. The launcher uses Termux's permission-protected RUN_COMMAND service with one fixed script and working directory. The script holds a file lock, starts Node, acquires a wake lock and releases it on shutdown. The health probe checks both reachability and `runtime: tablet`; a reachable workstation cannot masquerade as the local engine. The existing HTTPS workstation option remains separate.

The companion `com.adamgoodwin.galaxyreader`, version **0.2.0**, is labelled **Galaxy Device Tools**. Its Accessibility service reads and navigates the visible Outlook UI and provides bounded Android device APIs. It listens exclusively on authenticated loopback, 127.0.0.1:48442. Private key provisioning, device identity pinning and lifecycle setup are documented in the runbook. The older ADB instrumentation reader remains for optional workstation mode.

## Permissions and boundaries

- Main app: INTERNET and Termux RUN_COMMAND. No microphone, camera, broad storage or JavaScript/native bridge. Android pickers grant access only to selected documents.
- Helper: INTERNET for local IPC; Accessibility activation for visible Outlook reading/navigation; WRITE_SETTINGS and the user-authorized development WRITE_SECURE_SETTINGS grant for the four allowlisted settings; QUERY_ALL_PACKAGES for the requested app inventory. No arbitrary shell, app launches, mail sending, event edits or private-app-data access.
- The helper rejects incorrect bearer credentials, browser Origin headers, wrong Host, unsupported operations and stale Outlook controls. Requests, snapshots and execution times are bounded. Diagnostic logs contain lifecycle/status only, not request content or keys.
- HTTP is permitted only for localhost in the main app; the origin policy narrows it to port 4318. Other configured origins require HTTPS. Third-party cookies, mixed content, file/content browsing and certificate bypass are blocked.
- Downloads accept only exact same-origin export or workspace-source endpoints, allowed formats and bounded size/time. Cookies never follow redirects. Saving uses ACTION_CREATE_DOCUMENT; opening/sharing uses a narrow FileProvider directory and temporary read grants. Uploads use ACTION_OPEN_DOCUMENT. Office edits must be saved as a separate copy and explicitly re-imported.
- Private handoff copies expire after seven days on the next transfer; at most 20 transfer directories are retained. Last saved file retains a selected document URI/name where the provider permits it. Export save receipts are recorded only after the output stream closes successfully. Opening a share chooser never claims that anything was sent.
- Reconnect this tablet invokes the same fixed Termux script with the fixed --pair argument. A one-time 60-second ticket returns through an explicit, unexported PendingIntent receiver and native loopback POST; it never enters a URL, clipboard or JavaScript. The private engine stores only its hash and consumes it before issuing the HttpOnly cookie. Native startup waits for the tablet engine before loading cached UI.
- App backup/transfer is disabled. Termux owns private runtime files; preserving its data is essential during upgrades. Debug WebView inspection is development-build-only.

## Build and update

`./galaxy android-build` assembles both APKs, runs eight launcher/transfer-policy unit tests and Android lint. It is bounded to ten minutes with one Gradle worker. AGP 8.12.0, Gradle 8.13 with checksum verification, Java 17. SDK, builds, signing keys and APKs are ignored.

Install each APK with `adb install -r`, keeping the same signing key. Do not use the legacy `android-install` command in independent mode: its USB reverse mapping would interfere with the tablet's own localhost service. Transfer the production JS bundle and server/scripts into Termux while preserving its private data and credentials.

Two helper lint suppressions are explicitly scoped in its manifest: the development settings grant and installed-package inventory. They document this authorized local pilot's requirements; they do not disable lint generally or establish Play Store eligibility.

## Verification

See the current [verification record](2026-09-22%20-%20Verification.md). On the actual SM-X810, the standalone app opened the local runtime with retained history; Codex assessed sample sources and saved a report; both connected OneDrive roots loaded; Word/PDF export, native settings Apply/Undo, shared-folder listing and Outlook calendar/search were exercised. Earlier checks covered document pickers, keyboard visibility, rotation, origin policy, cold app restart and source-link previews. Spoken dictation and a full day of field use remain user tests.

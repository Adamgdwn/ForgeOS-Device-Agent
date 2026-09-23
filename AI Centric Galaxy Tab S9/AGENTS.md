# Galaxy Workspace

Last Updated: 2026-09-22

This subproject has a native Android shell and a browser client. At Adam's explicit request on 2026-09-22, its independent tablet runtime uses Termux, a local Codex login and authenticated loopback device tools. The optional workstation runtime remains supported. There is no flashing or dependency on the ForgeOS runtime.

- Preserve parent-repository changes. Run its governance preflight before substantial changes.
- Run `npm run build` and `npm test`; verify browser flows after UI changes.
- For Android changes run `./galaxy android-build` (APK, origin-policy unit tests, lint) and check the actual tablet. The Android shell embeds the existing workspace; do not claim a fully native chat UI.
- Keep Android builds and local SDK/signing configuration ignored. Never add a JavaScript/native bridge, arbitrary HTTP, or certificate bypass. Tablet shared-file access is bounded to visible public folders and excludes Android/private paths. The launcher may invoke only the fixed local Termux engine script.
- Keep runtime databases, pairing credentials, tokens, imported documents, and workspaces in ignored `.local/`.
- Never expose Codex stdio/RPC directly to the browser or forward arbitrary RPC methods.
- Microsoft accounts are independent connections. Preserve source account/drive/item/version on imports.
- Model statements are not verification evidence. Show command results and diffs separately.
- A disconnected browser must not restart work. Never automatically retry an ambiguous worker submission.
- Treat app-server as an experimental pinned integration; check generated installed schemas before upgrades.
- System means the Galaxy tablet, not the Linux host. Its worker has shell disabled and a read-only sandbox. Keep tablet tools typed and bind every operation to the configured device serial/model or local helper identity. All Android workers use typed tools with shell disabled; PRoot supplies a resolver-file compatibility binding, not a security sandbox.
- Tablet setting changes require a persisted before/after proposal, an explicit Apply action, a current-value conflict check, read-back verification and conditional Undo. Never retry an uncertain write or add arbitrary ADB/shell execution, private app-data access, deletion, rooting or flashing to this flow.
- Assistant and meeting workspaces use typed Outlook reading and local briefing tools with shell disabled. The Android helper reads and navigates only the visible Outlook hierarchy through Accessibility. Its authenticated HTTP service binds exclusively to 127.0.0.1 and rejects browser origins. The secret stays in private app storage. Navigation uses fresh item references. User-authorized development settings grants expose only the four existing reviewed settings; package visibility supports the requested app inventory. Keep the helper free of account access, private storage access and arbitrary shell execution. No arbitrary coordinates, app launches, message sending, invitation responses, links or account changes may be exposed to the model.
- The opt-in Code workspace uses typed `workspace_files`, `workspace_read`, hash-checked direct `workspace_edit`, and `workspace_command`. Built-in Codex shell remains disabled on Android. Every exact terminal command requires a fresh in-app user approval; decline, interruption and restart never execute it. Commands run as Termux's UID without an OS sandbox and may access Termux private data and the network. Show this clearly in the approval card and never describe commands as workspace-confined. Do not weaken the per-command gate or offer command execution in Assistant, System or document workspaces. Direct file edits are limited to visible, nonsymlink plain-text paths in the managed Code workspace.
- Surface Outlook sign-in/offline/loading warnings and partial coverage. A cached event is not proof of current calendar access; opening email can mark it read. Never claim a meeting brief was saved or uploaded without its actual receipt. Local meeting folders and OneDrive exports are separate operations.

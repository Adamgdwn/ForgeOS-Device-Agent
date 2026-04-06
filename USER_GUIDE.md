# ForgeOS Device Agent User Guide

## What ForgeOS Is

ForgeOS Device Agent is a Pop!_OS desktop launcher for a local autonomous Android device runtime.

The runtime is designed to:

- detect an attached phone
- create a per-device execution session
- assess transport and hardware clues
- stage real install artifacts for the chosen rebuild path
- prepare recovery and backup artifacts
- classify blockers
- keep moving automatically while the blocker is software-solvable
- stop only when a real human action, destructive approval, missing external artifact, or hard technical limit is reached

The GUI is an operator monitor. It is not the main engine.

## What This Build Can Do Today

This checkpoint is ready for:

- desktop launch
- best-effort VS Code sidecar opening
- first-run host bootstrap
- device session creation
- persistent state tracking
- initial hardware and transport assessment
- per-session recovery bundle and restore-plan generation
- staged install artifact intake under each session
- flashable artifact manifest and bundle generation
- explicit wipe-approval capture
- approved dry-run flash execution
- generic live execution for staged `fastboot` image sets or `adb sideload` packages
- simplified operator monitor mode
- optional advanced-details mode

This build is intended to be shipped for a controlled supported scope:

- generic `fastboot` image installs when the session has a staged `.img` set
- generic `adb sideload` installs when the session has a staged OTA-style zip
- operator-reviewed, explicitly approved wipe-and-rebuild execution

It is not yet a universal cross-OEM unattended flasher for unknown devices without further device-family integration.

## Safety First

Before connecting a test phone, assume the following:

- every phone is unsupported until proven otherwise
- recovery matters more than speed
- bootloader unlock, flashing, relocking, and signing decisions must be deliberate
- the current scaffold defaults to non-destructive planning

Use a test phone you can afford to lose data on.

Do not use your primary phone for first validation.

## What Happens On Launch

When you open ForgeOS from the Pop!_OS app menu:

1. The launcher starts the ForgeOS runtime.
2. ForgeOS bootstraps the local workspace.
3. The main VS Code workspace opens if `code` is available.
4. Background watchers begin checking for `adb`, `fastboot`, and USB-only Android visibility.
5. The operator monitor opens in a simplified view.

## Reading The Operator Monitor

By default, focus on these panels only:

1. `Runtime Mission`
2. `Agent Execution`
3. `Autonomous Self-Heal`
4. `1. Intake And Autonomy Limits`
5. `2. Proposed Outcome And Preview`
6. `3. Backup And Restore`
7. `4. Build Artifacts`
8. `6. Install Gate`

These are the two questions ForgeOS is trying to answer for you:

- what has the runtime already done
- what is the one thing you need to do next, if anything

At the top of the window, the status line now includes a spinning radioactive symbol when ForgeOS is actively working.

Use that indicator as a quick heartbeat:

- spinning `☢` means ForgeOS is actively scanning, refreshing, or recomputing the session
- dim `☢` means ForgeOS is idle and waiting for the next device event or operator action

The `Autonomous Self-Heal` panel now reports when ForgeOS detects a repeated local-worker failure, what it retried, and whether the bounded fix loop recovered the task.

ForgeOS now gives the local workers up to three autonomous fix rounds before it asks for help. If that is still not enough, it pauses and asks for permission for another batch of three through `Approve 3 More Fix Loops`.

When ForgeOS is simply in `recommendation` or `research_only_path` with no real machine-solvable blocker, it should now stay in honest research mode instead of generating a no-op remediation artifact.

Use `Show Advanced Details` only when you want the deeper session dump, execution queue, and other lower-level diagnostics.

## What To Do When A Phone Is Connected

If a phone is already connected and ForgeOS shows it as live:

1. Read `Runtime Mission`.
2. Check `Agent Execution`.
3. If the phone is fully connected over `adb`, leave it connected and unlocked.
4. Set the intended user profile only if you want a different OS strategy.
5. Do not approve a wipe until you are satisfied with the backup and flash plan.

If ForgeOS needs something from you, the top panels should now reduce that to one next action.

## Destructive Approval Flow

ForgeOS includes a dedicated approval panel in the GUI.

Use it like this:

1. Let ForgeOS assess the phone and generate a flash plan.
2. Review the flash plan and restore assumptions.
3. Confirm that you have reviewed the restore path.
4. Type `WIPE_AND_REBUILD`.
5. Click `Record Wipe Approval`.
6. Run the approved dry run first.

By default, live destructive execution is still blocked by policy in:

- [default_policy.json](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/master/policies/default_policy.json)

That policy must be changed deliberately before the GUI will allow a live wipe-and-flash attempt.

## Connection Setup Guidance

When the phone is only visible as USB or MTP, ForgeOS should:

- identify the vendor and model when possible
- show phone-side setup steps for that family
- tell you the expected next state, such as `adb unauthorized` or `adb connected`
- give a few troubleshooting steps before you try anything destructive

When the phone is already connected through `adb`, the connection setup panel may be hidden in simple mode because it is no longer the current blocker.

## Backup Before Wipe

Each session now creates a best-available pre-wipe recovery set under the device folder:

- `backup/backup-plan.json`
- `backup/device-metadata-backup.json`
- `backup/session-recovery-bundle.tar.gz`
- `restore/restore-plan.json`

What this means in practice:

- `backup/session-recovery-bundle.tar.gz` preserves host-side session intelligence and recovery evidence
- `backup/device-metadata-backup.json` preserves the best available live phone metadata capture
- `restore/restore-plan.json` records how ForgeOS intends to recover safely if something goes wrong

This does not guarantee a full firmware restore for every device family.
It does guarantee that ForgeOS preserves the best available session intelligence, transport facts, metadata capture, and recovery notes before a destructive step is approved.

## Build Artifact Staging

ForgeOS now expects real install inputs to be staged per session under:

- `artifacts/os-source/`

Supported generic install inputs:

- `update.zip`, `ota.zip`, or `payload.zip` for `adb sideload`
- fastboot images such as `boot.img`, `system.img`, `vendor.img`, `vbmeta.img`, or `super.img`

When these files are present, ForgeOS creates:

- `runtime/build/artifact-manifest.json`
- `runtime/build/flashable-artifacts.tar.gz`
- `runtime/build/README.md`

The GUI `4. Build Artifacts` panel shows:

- whether the artifact set is ready
- which install mode ForgeOS will use
- which files were staged
- what still needs to be provided before install can proceed

## Install And Reinstall The Launcher

The launcher is installed into your local applications directory:

- [forgeos.desktop](/home/adamgoodwin/.local/share/applications/forgeos.desktop)

If you move the repo or want to refresh the launcher:

```bash
bash scripts/install_launcher.sh
```

## Start ForgeOS Manually

If you want to start it from a terminal:

```bash
./launcher/launch_forgeos.sh
```

Or:

```bash
.venv/bin/python -m app.main
```

## Host Readiness Check

Run this before your first real test session:

```bash
bash scripts/verify_environment.sh
```

Expected good signs:

- `code` is found
- `adb` is found
- `fastboot` is found
- `venv python` is found
- `udev-like device paths` are present

## First Device Test Workflow

Use this sequence with your test phone.

### 1. Prepare The Phone

- Charge it above 50%.
- Use a good USB data cable.
- If Android boots normally, enable Developer Options and USB debugging.
- If possible, record the exact model, current Android version, and whether the bootloader is known to be unlockable.

### 2. Start ForgeOS

Open ForgeOS from the desktop icon or run:

```bash
./launcher/launch_forgeos.sh
```

### 3. Connect The Phone

Attach the device by USB.

ForgeOS will try to detect:

- `adb` mode
- `fastboot` mode
- `fastbootd` transitions

### 4. Approve USB Debugging If Prompted

If Android presents an RSA trust prompt, approve it on the phone.

### 5. Confirm Device Detection

You can verify transport manually:

```bash
local-tools/platform-tools/adb devices -l
```

Or:

```bash
local-tools/platform-tools/fastboot devices
```

### 6. Inspect The New Session Folder

A newly detected phone creates a deterministic session under `devices/`:

```text
devices/{manufacturer}-{model}-{short-fingerprint}-{date}/
```

Important files:

- `device-profile.json`
- `session-state.json`
- `reports/assessment.json`
- `reports/engagement.json`
- `plans/master-strategies/`
- `plans/connection-plan.json`
- `backup/backup-plan.json`
- `backup/device-metadata-backup.json`
- `backup/session-recovery-bundle.tar.gz`
- `restore/restore-plan.json`
- `execution/flash-plan.json`

### 7. Review The Session State

The first automatic state is no longer a simple `ASSESS` shortcut.
The runtime now moves through persisted states such as:

- `DEVICE_ATTACHED`
- `DISCOVER`
- `PROFILE_SYNTHESIS`
- `BACKUP_PLAN`
- `PATH_SELECT`
- `BLOCKER_CLASSIFY`
- `QUESTION_GATE`

Check it here:

- [session_manager.py](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/app/core/session_manager.py)
- [state_machine.py](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/app/core/state_machine.py)

### 8. Read The Assessment Result

ForgeOS currently classifies the device into one of:

- `actionable`
- `research_only`
- `blocked`
- `experimental`

If the device is `blocked` or `research_only`, that is a correct and safe outcome when restore or support feasibility is not proven.

### 9. Read The Runtime Result

ForgeOS now attempts safe, non-destructive runtime steps automatically.

That includes:

- starting the adb server
- retrying adb reconnect
- checking whether the phone is visible only as USB/MTP
- collecting hardware clues through live `adb` when available
- generating backup and restore artifacts
- classifying whether the next blocker is machine-solvable or requires you

This does not mean ForgeOS can bypass a locked screen or trust prompt.

### 10. Set The User Profile

ForgeOS includes a profile section in the GUI for each device session.

Set:

- intended user persona
- technical comfort
- top priority
- Google-services preference
- secondary OS goal

Then save the profile to recompute the recommended OS path for that exact device and intended user.

This updates:

- `user-profile.json`
- `os-goals.json`
- `session-state.json`
- `plans/connection-plan.json`

## Where To Look During Testing

### Session Files

Each device has its own workspace under:

- [devices/](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/devices)

### Audit Logs

Tool executions are recorded under:

- [logs/](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/logs)

### Bootstrap Reports

Host bootstrap reports are stored under:

- [output/](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/output)

### Master Framework

Reusable policy and strategy assets live under:

- [master/](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/master)

### Knowledge And Promotion

ForgeOS now improves through controlled evidence capture.

- [knowledge/](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/knowledge) stores session outcomes and the support matrix
- [promotion/](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/promotion) stores promotion rules and review-required master update candidates

This means the system can get better at recommendations over time without silently changing risky behavior.

## Recommended First Phone Test

Use a straightforward validation pass first:

1. Launch ForgeOS.
2. Connect the phone in normal Android mode with USB debugging enabled.
3. Confirm the device appears in `adb devices -l`.
4. Confirm ForgeOS creates a new session folder.
5. Open `device-profile.json` and `session-state.json`.
6. Verify the session enters persisted runtime states such as `DEVICE_ATTACHED`, `DISCOVER`, `PROFILE_SYNTHESIS`, and `QUESTION_GATE` or later.
7. Review `assessment.json` and confirm the support classification makes sense.

Do not try live flashing from this first pass.

Use it to validate detection, fingerprinting, logging, naming, and session isolation.

## Common Problems

### The App Launches But No Phone Appears

- Try a different USB cable.
- Confirm the phone is in data mode, not charge-only mode.
- Run `adb devices -l`.
- Toggle USB debugging off and on.
- Reconnect the phone and approve the RSA dialog again.

### The Phone Only Appears In Fastboot

That can still be useful.

Run:

```bash
local-tools/platform-tools/fastboot devices
```

ForgeOS can still create a session from fastboot visibility, but the assessment may remain limited.

### VS Code Does Not Open

The app continues running even if `code` is unavailable.

Check:

```bash
command -v code
```

### No Session Folder Is Created

Review:

- [adb_watcher.py](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/app/watchers/adb_watcher.py)
- [fastboot_watcher.py](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/app/watchers/fastboot_watcher.py)
- [orchestrator.py](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/app/core/orchestrator.py)

Then check audit logs in:

- [logs/](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/logs)

## Current Limits You Should Expect

Right now ForgeOS is strongest at:

- environment bootstrap
- device session management
- state persistence
- safety-oriented assessment scaffolding
- repeatable per-device isolation

It is still intentionally incomplete for:

- fully automated hardware-aware OS builds across arbitrary Android devices
- broad device-family flashing adapters
- full Android source resolution
- AVB signing integration
- unattended live wipe/flash execution on unknown hardware
- modem, Wi-Fi, Bluetooth, and OTA validation

Those live integration tasks are tracked in:

- [NEXT_STEPS.md](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/NEXT_STEPS.md)

## Best Next Move With Your Test Phone

Use the phone to validate the assessment pipeline first.

The fastest meaningful test is:

1. Launch ForgeOS.
2. Connect the phone in Android with USB debugging enabled.
3. Confirm a session folder is created.
4. Share the generated `device-profile.json` and `session-state.json`.

From there we can wire the next layer of live probing around your exact device rather than pretending all phones behave the same way.

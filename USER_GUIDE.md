# ForgeOS Device Agent User Guide

## What ForgeOS Is

ForgeOS Device Agent is a Pop!_OS desktop control application for assessing Android phones, creating isolated per-device workspaces, and planning the safest feasible custom OS path from a reusable master framework.

The current build is assessment-first. It is ready for:

- desktop launch
- VS Code workspace opening
- first-run host bootstrap
- device session creation
- persistent state tracking
- dry-run strategy selection
- audit logging
- explicit wipe-approval capture
- approved dry-run flash execution planning
- model-aware connection setup guidance
- automatic session backup bundle and restore-plan generation

It is not yet ready for unattended live flashing across unknown devices without additional device-specific integration work.

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

1. The launcher starts the ForgeOS control app.
2. ForgeOS bootstraps the local workspace.
3. The main VS Code workspace opens if `code` is available.
4. Background watchers begin checking for `adb` and `fastboot` devices.
5. The desktop app shows host readiness and launch status.

## Destructive Approval Flow

ForgeOS now includes a dedicated approval panel in the GUI.

Use it like this:

1. Let ForgeOS assess the phone and generate a flash plan.
2. Review the current blocker, build path, and restore assumptions.
3. Confirm that you have reviewed the restore path.
4. Type `WIPE_AND_REBUILD`.
5. Record the approval.
6. Run the approved dry run first.

By default, live destructive execution is still blocked by policy in:

- [default_policy.json](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/master/policies/default_policy.json)

That policy must be changed deliberately before the GUI will allow a live wipe-and-flash attempt.

## Connection Setup Guidance

ForgeOS now includes a model-aware connection setup panel.

When the phone is only visible as USB or MTP, ForgeOS should:

- identify the vendor and model when possible
- show phone-side setup steps for that family
- tell you the expected next state, such as `adb unauthorized` or `adb connected`
- give a few troubleshooting steps before you try anything destructive

For supported matches such as the Samsung Galaxy A5, the instructions are more specific than the generic Android fallback.

## Backup Before Wipe

Each session now creates a best-available pre-wipe backup set under the device folder:

- `backup/backup-plan.json`
- `backup/device-metadata-backup.json`
- `backup/session-recovery-bundle.tar.gz`
- `restore/restore-plan.json`

This does not guarantee a full firmware restore for every device family.
What it does guarantee is that ForgeOS preserves the best available session intelligence, transport facts, metadata capture, and recovery notes before a destructive step is approved.

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
- `codex/CODEX_TASK.md`
- `codex/codex-handoff.json`
- `codex/device-session.code-workspace`

### 7. Review The Session State

The first automatic state should be `ASSESS`.

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

### 9. Read The Autonomous Engagement Result

ForgeOS now attempts safe, non-destructive engagement steps automatically.

That includes:

- starting the adb server
- retrying adb reconnect
- checking whether the phone is visible only as USB/MTP
- recording the exact point where on-device approval is still required

This does not mean ForgeOS can bypass a locked screen or hidden developer settings.

If the phone still requires a trust prompt, USB debugging, or a different boot mode, ForgeOS will stop honestly and tell you what is still needed.

### 10. Use The Codex Handoff

ForgeOS now prepares a device-specific Codex build brief automatically.

That brief tells Codex:

- what phone is attached
- what transport is available
- what connection adapters are most promising
- what still needs to be generated or refined for this exact device

The session workspace file is:

- `codex/device-session.code-workspace`

The primary human-readable task file is:

- `codex/CODEX_TASK.md`

This is the main path for building device-specific connection logic and custom OS preparation from first principles while preserving the reusable `master/` framework.

### 11. Set The User Profile

ForgeOS now includes a guided profile section in the GUI for each device session.

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
- `codex/CODEX_TASK.md`

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
6. Verify the session starts in `ASSESS`.
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

- real per-device partition discovery
- factory image restore proofing
- full Android source resolution
- AVB signing integration
- actual flash execution
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

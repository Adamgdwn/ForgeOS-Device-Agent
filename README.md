# ForgeOS Device Agent

ForgeOS Device Agent is a Pop!_OS desktop-launchable control environment for assessing attached Android phones, creating per-device sessions, and selecting the safest feasible custom OS path from a reusable master framework.

## Architecture Choices

- Python-first orchestration with explicit persisted state transitions.
- Master/session split so reusable logic lives in `master/` and every phone gets its own isolated workspace under `devices/`.
- Safety-first execution with dry-run destructive tooling by default.
- Connectivity-first probing so transport, recovery, and restore viability are established before build ambition.
- Structured JSON artifacts and JSON Schema contracts for auditability and crash recovery.
- Controlled learning through `knowledge/` and `promotion/`, where session evidence improves support guidance without silently mutating policy.

## Repo Structure

```text
forgeos/
  launcher/
  app/
    core/
    watchers/
    tools/
    integrations/
    schemas/
  master/
  knowledge/
  promotion/
  devices/
  logs/
  output/
  scripts/
  tests/
```

## State Machine

The persisted state machine is:

`IDLE -> DISCOVER -> ASSESS -> BACKUP_PLAN -> UNLOCK_PREP -> UNLOCK -> BASELINE_CAPTURE -> PATH_SELECT -> BUILD_GENERIC -> BUILD_DEVICE -> SIGN_IMAGES -> FLASH_PREP -> FLASH -> BOOTSTRAP_DEVICE -> BRINGUP -> HARDEN -> VALIDATE -> PROMOTE`

Exceptional or alternate flows:

- Any state can transition to `BLOCKED` on red-flag conditions.
- `VALIDATE` can transition to `RESTORE` if validation fails and recovery is feasible.
- `RESTORE` transitions to `BLOCKED` or `ASSESS` depending on outcome.
- Crash recovery resumes from the last persisted safe state in `session-state.json`.

## Launch

Use the desktop launcher in `launcher/forgeos.desktop` or start the app manually:

```bash
python -m app.main
```

## Operator Guide

For launch, testing, and first-device workflow instructions, see [USER_GUIDE.md](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/USER_GUIDE.md).

## Current Scope

This scaffold is runnable and auditable. Live Android build, signing, and flashing implementations remain stubbed behind explicit tool contracts so they can be integrated without collapsing the safety model.

The learning layer now records session outcomes, builds a device-family support matrix, and generates review-only promotion candidates for the master framework.

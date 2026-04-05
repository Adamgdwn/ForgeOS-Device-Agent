# ForgeOS Device Agent

ForgeOS Device Agent is a Pop!_OS desktop-launchable control environment for assessing attached Android phones, creating per-device sessions, and selecting the safest feasible custom OS path from a reusable master framework.

The current build now includes an operator approval surface for destructive work: each session can generate a flash plan, capture explicit wipe approval, and run an approved dry run while live destructive execution remains policy-blocked by default.

## Architecture Choices

- Python-first orchestration with explicit persisted state transitions.
- Master/session split so reusable logic lives in `master/` and every phone gets its own isolated workspace under `devices/`.
- Safety-first execution with dry-run destructive tooling by default.
- Connectivity-first probing so transport, recovery, and restore viability are established before build ambition.
- Structured JSON artifacts and JSON Schema contracts for auditability and crash recovery.
- Controlled learning through `knowledge/` and `promotion/`, where session evidence improves support guidance without silently mutating policy.
- Autonomous non-destructive engagement attempts so USB-only phones can still be assessed and guided toward adb or fastboot transport when possible.
- Per-session Codex handoff generation so each detected device opens into a VS Code workspace with a structured build brief and connection plan.
- Guided user-profile intake so OS path selection can account for seniors, developers, daily users, children, and privacy-focused profiles.
- Explicit destructive approval capture plus approved dry-run flash execution planning.
- Model-aware connection playbooks and automatic pre-wipe backup bundle generation.

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

The persisted state machine is currently centered on this runtime path:

`IDLE -> DEVICE_ATTACHED -> DISCOVER -> PROFILE_SYNTHESIS -> ASSESS -> MATCH_MASTER -> PATH_SELECT -> BLOCKER_CLASSIFY -> CODEGEN_TASK -> PATCH_APPLY -> EXECUTE_STEP -> QUESTION_GATE -> FLASH_PREP -> FLASH`

Exceptional or alternate flows:

- Any state can transition to `BLOCKED` on red-flag conditions.
- `QUESTION_GATE` now represents approval or physical-action waits, including destructive wipe approval.
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

This scaffold is runnable and auditable. It can now:

- assess and persist device sessions
- classify blockers and write execution reports
- capture explicit destructive approval per session
- generate a flash plan and execute an approved dry run

Live Android build, signing, and hardware-specific flashing implementations still remain partially stubbed behind explicit tool contracts so they can be integrated without collapsing the safety model.

The learning layer now records session outcomes, builds a device-family support matrix, and generates review-only promotion candidates for the master framework.

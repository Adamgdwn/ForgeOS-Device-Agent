# ForgeOS Device Agent

ForgeOS Device Agent is a Pop!_OS desktop-launchable autonomous Android device runtime. It detects attached phones, creates per-device execution sessions, interrogates hardware and transport state, classifies blockers, writes remediation artifacts, and keeps moving until it reaches a real human-action, approval, artifact, or hard technical boundary.

The current build includes a simplified operator monitor, explicit wipe approval capture, per-session flash planning, pre-wipe recovery bundle generation, and approved dry-run execution while live destructive execution remains policy-blocked by default.

## Architecture Choices

- Python-first orchestration with explicit persisted state transitions.
- Master/session split so reusable logic lives in `master/` and every phone gets its own isolated execution workspace under `devices/`.
- Safety-first execution with dry-run destructive tooling by default.
- Connectivity-first probing so transport, recovery, and restore viability are established before build ambition.
- Structured JSON artifacts and JSON Schema contracts for auditability and crash recovery.
- Controlled learning through `knowledge/` and `promotion/`, where session evidence improves support guidance without silently mutating policy.
- Blocker-driven remediation so machine-solvable blockers create runtime tasks instead of stopping at guidance.
- Session-local codegen, execution, and patch registration for remediation artifacts.
- Best-effort VS Code sidecar opening on launch and on session activation, without making VS Code the center of the product.
- Simplified operator monitor UI with an optional advanced-details view.
- Explicit destructive approval capture plus approved dry-run flash execution planning.
- Pre-wipe recovery bundle, live device metadata backup, and restore-plan generation per session.

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

The persisted state machine is now centered on an autonomous remediation loop:

`IDLE -> DEVICE_ATTACHED -> DISCOVER -> PROFILE_SYNTHESIS -> MATCH_MASTER -> BACKUP_PLAN -> PATH_SELECT -> BLOCKER_CLASSIFY -> REMEDIATION_DECIDE -> TASK_CREATE -> CODEGEN_WRITE -> PATCH_APPLY -> EXECUTE_ARTIFACT -> INSPECT_RESULT`

From there the runtime either:

- returns to `BLOCKER_CLASSIFY` for another remediation cycle
- moves forward to `CONNECTIVITY_VALIDATE` or later execution states
- enters `QUESTION_GATE` for minimal human interaction
- or halts in `BLOCKED`

Important rules:

- Every transition is persisted.
- Crash recovery resumes from the last safe persisted state in `session-state.json`.
- Destructive operations remain dry-run by default until approval is captured.
- Connectivity and recovery evidence are gathered before destructive actions are considered.

## Launch

Use the desktop launcher in `launcher/forgeos.desktop` or start the app manually:

```bash
python -m app.main
```

## Operator Guide

For launch, testing, and first-device workflow instructions, see [USER_GUIDE.md](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/USER_GUIDE.md).

## Current Scope

This checkpoint is runnable and auditable. It can now:

- detect Android-family devices over USB, `adb`, and `fastboot`
- create or resume per-device execution sessions
- assess transport and initial support feasibility
- refresh live hardware evidence from `adb`
- generate host-side recovery bundles and restore plans
- classify blockers and execute remediation artifacts for machine-solvable runtime issues
- persist flash plans and destructive approval state
- run approved dry-run execution paths
- surface the current runtime objective in a simplified operator monitor

What is still incomplete:

- full hardware-aware OS build automation for arbitrary devices
- device-family flashing adapters across the Android ecosystem
- unattended live wipe/flash/validate loops on real hardware
- robust session renaming when an early coarse identity later becomes precise

The learning layer records session outcomes, builds a support matrix, and generates review-only promotion candidates for the master framework.

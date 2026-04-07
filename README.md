# ForgeOS Device Agent

ForgeOS Device Agent is a Pop!_OS desktop-launchable autonomous Android device runtime. It detects attached phones, creates per-device execution sessions, interrogates hardware and transport state, routes work to the right worker tier, classifies blockers, writes remediation artifacts, and keeps moving until it reaches a real human-action, approval, artifact, or hard technical boundary.

The current build includes a runtime-first session model, a GUI control surface, explicit wipe approval capture, per-session flash planning, pre-wipe recovery bundle generation, use-case recommendation, worker routing, and approved dry-run execution while live destructive execution remains policy-blocked by default.

## Architecture Choices

- Python-first orchestration with explicit persisted state transitions.
- Runtime-first design where the GUI is a shell over the device-session runtime.
- Master/session split so reusable logic lives in `master/` and every phone gets its own isolated execution workspace under `devices/`.
- Safety-first execution with dry-run destructive tooling by default.
- Connectivity-first probing so transport, recovery, and restore viability are established before build ambition.
- Structured JSON artifacts and JSON Schema contracts for auditability and crash recovery.
- Controlled learning through `knowledge/` and `promotion/`, where session evidence improves support guidance without silently mutating policy.
- OEM-specific adapters and playbooks are additive. The default runtime path should remain generic unless live evidence matches a brand-specific branch.
- Learned runtime knowledge is persisted locally. If you want a clean evaluation across brands, clear or isolate `knowledge/` and `promotion/` before testing.
- Blocker-driven remediation so machine-solvable blockers create runtime tasks instead of stopping at guidance.
- Session-local codegen, execution, and patch registration for remediation artifacts.
- Retry heat tracking so repeated non-advancing remediation cycles escalate instead of looping forever.
- Autonomous experiment logging so self-heal attempts can be advanced or discarded instead of silently retried.
- Trusted source acquisition with research TTL checks and conservative firmware provenance rules.
- Explicit worker routing across frontier reasoning, local general execution, local editing, and deterministic policy checks.
- VS Code integration is optional and should be operator-invoked, not opened automatically as part of the runtime path.
- Simplified operator monitor UI that surfaces runtime state, approvals, evidence, and worker routing.
- Explicit destructive approval capture plus approved dry-run flash execution planning.
- Pre-wipe recovery bundle, live device metadata backup, and restore-plan generation per session.
- Best-use-case recommendation so each device can be matched to a practical rehabilitation target instead of a one-size-fits-all build path.

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

The newer runtime-first flow extends this with explicit intake and execution stages:

`DEVICE_ATTACHED -> INTAKE -> ACCESS_ENABLEMENT -> DEEP_SCAN -> ASSESS -> RECOMMEND -> BACKUP_PLAN -> BACKUP_READY -> PREVIEW_BUILD -> PREVIEW_REVIEW -> INTERACTIVE_VERIFY -> INSTALL_APPROVAL -> FLASH -> POST_INSTALL_VERIFY`

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
- Install planning is now gated through deterministic policy logic, not model judgment alone.
- Repeated `ITERATE` landings escalate to `DEEP_SCAN` so the runtime refreshes live device facts instead of idling.
- Waiting sessions in `QUESTION_GATE` resume when the same device reappears with new state.

## Runtime Artifacts

Each device session can now persist runtime-first artifacts under `devices/<session>/runtime/`:

- `session-plan.json`
- `worker-routing.json`
- `runtime-audit.json`

These files are intended to give both the GUI and future automation a durable, auditable view of the runtime’s current intent.

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
- persist retry heat so the same blocker cannot silently loop forever
- re-enter stalled sessions when a waiting device changes transport or state
- deep-scan live devices after repeated non-advancing iterate cycles
- resolve firmware sources conservatively with TTL-aware research and trusted-host download checks
- persist flash plans and destructive approval state
- route work across explicit worker tiers
- generate best-use-case recommendations and runtime session plans
- run approved dry-run execution paths
- surface the current runtime objective in a simplified operator monitor

What is still incomplete:

- full hardware-aware OS build automation for arbitrary devices
- device-family flashing adapters across the Android ecosystem
- unattended live wipe/flash/validate loops on real hardware
- robust session renaming when an early coarse identity later becomes precise
- complete remote source provenance verification beyond conservative host and size checks

The learning layer records session outcomes, builds a support matrix, and generates review-only promotion candidates for the master framework.

## Next Steps

The next highest-value work is to keep turning ForgeOS into an explicit autonomous research-and-repair loop instead of a smart blocker dashboard.

Near-term priorities:

- Build on the new experiment ledger so every remediation path has a measurable `advance` or `discard` outcome, similar in spirit to Karpathy's `autoresearch` keep-or-revert loop.
- Teach source acquisition to rank and compare multiple firmware candidates instead of taking the first locally or remotely trusted match.
- Make preview generation consume accepted and rejected features so the preview output changes when the operator changes the plan.
- Replace more simulated preview content with concrete generated UI walkthroughs, capability summaries, and build-specific artifacts.
- Expand backup visibility so the operator can inspect bundle contents, restore steps, and rollback confidence more directly from the GUI.
- Tighten install gating copy and sequencing so destructive actions feel clearly late-stage and never central to the experience.
- Continue improving brand-agnostic behavior by keeping OEM-specific paths additive and evidence-triggered only.
- Keep local-worker execution efficient by preferring lightweight runtime passes, artifact reuse, and minimal frontier escalation.

If you are resuming after a break, the best starting point is to test one full recommendation-to-review cycle and confirm that:

- the runtime writes `reports/autonomous-experiments.json` when it self-heals
- source blockers stay autonomous long enough to attempt real staging and research
- the proposed OS summary stays aligned with the current recommendation
- feature keep/reject choices persist
- the preview and review panels feel trustworthy before any install gate appears

Latest end-of-day testing note:

- ForgeOS is now clearly performing autonomous worker and firmware-research activity on live sessions, but one remaining gap is that some full recompute runs still do not land their final remediation outputs back into `reports/autonomous-experiments.json` and `plans/source-acquisition-plan.json`.
- The next best debugging target is to trace why a long-running full runtime recompute can spend time in workers and research yet fail to complete the final session-artifact writeback for the active session.

## Release Notes

- Runtime-first architecture overview: [docs/runtime-architecture.md](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/docs/runtime-architecture.md)
- Sprint-ready roadmap: [docs/sprint-plan.md](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/docs/sprint-plan.md)
- Changelog: [CHANGELOG.md](/home/adamgoodwin/code/agents/ForgeOS%20Device%20Agent/CHANGELOG.md)

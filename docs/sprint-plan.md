# ForgeOS Sprint-Ready Plan

## Sprint 1: Runtime Core

- Finish migrating orchestration decisions into `runtime/session-plan.json`.
- Thread runtime phases through all session transitions.
- Add richer audit entries for retries, escalations, and approvals.
- Expose runtime phase, hard stops, and next actions in the GUI.

## Sprint 2: Local Worker Execution

- Add real command execution wrappers for Goose and Aider with output capture.
- Add Ollama-backed helper calls for summarization and repetitive reasoning.
- Record retry budgets and worker confidence per task.
- Add replayable remediation transcripts for local worker loops.

Status:
- Completed in the current branch, including transcript logging, retry telemetry, confidence scoring, adapter health artifacts, and host readiness discovery.

## Sprint 3: Device Discovery And Recommendation

- Expand deep scan with richer `adb shell getprop`, partition, slot, battery, and lock-state evidence.
- Improve use-case recommendation scoring with device capability and support-matrix research.
- Record verified facts separately from inferred feasibility.
- Present recommendation alternatives with evidence and constraints in the GUI.

## Sprint 4: Preview, Verification, And Install Gating

- Add emulator or simulated preview generation for the selected path.
- Add pre-install interactive verification checklists.
- Add post-install verification checkpoints and runtime confidence scoring.
- Gate install execution on deterministic policy checks and restore readiness only.

Status:
- Preview and verification now execute as real pipelines.
- Emulator-backed preview is attempted when the host supports it, with simulated fallback otherwise.
- Verification now records host-side and transport-aware checks.

## Sprint 5: Migration And Promotion

- Move generic session patterns into reusable framework modules.
- Keep device-specific overrides inside individual device sessions until proven reusable.
- Promote stable adapters and recommendation logic into the shared framework.
- Add regression tests for state progression, worker routing, backup gates, and install approvals.

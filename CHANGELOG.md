# Changelog

All notable changes to ForgeOS Device Agent will be documented in this file.

## Unreleased

### Added

- Retry heat tracking with per-session stall memory and escalation thresholds.
- Trusted source cache helpers and a TTL-aware source resolver for firmware candidate downloads.
- Focused tests for tool-blocking behavior, retry heat, source resolution, waiting-session resume, and promotion auditing.

### Changed

- Replaced silent tool stubs with explicit blocking or deferred results for critical runtime tools.
- Implemented real partition mapping, boot validator probing, and policy-gated bootloader unlock dispatch.
- Made waiting `QUESTION_GATE` sessions resume when the same device reconnects with new state.
- Added `ITERATE -> DEEP_SCAN` escalation so non-advancing runtime cycles force a fresh device probe.
- Added promotion deprecation and audit hooks so weakly evidenced promoted adapters can be flagged or retired.

## v0.2.0 - 2026-04-05

### Added

- Runtime-first worker architecture with explicit roles for:
  - `frontier_architect_worker`
  - `local_general_worker`
  - `local_editor_worker`
  - `policy_guard`
- Deterministic policy guard layer for destructive approval and restore gating.
- Runtime session planning artifacts under per-device `runtime/`.
- Best-use-case recommendation tool for rehabilitation-oriented device outcomes.
- Runtime architecture documentation in `docs/runtime-architecture.md`.
- Sprint-ready implementation roadmap in `docs/sprint-plan.md`.
- Focused tests for worker routing, policy gating, runtime planning, and the expanded state machine.

### Changed

- Refactored ForgeOS around a runtime-first session model instead of a UI-centered execution model.
- Expanded the state machine to cover:
  - intake
  - guided access enablement
  - deep scan
  - recommendation
  - backup readiness
  - preview planning
  - interactive verification
  - install approval
  - post-install verification
- Repositioned the GUI as a control surface for runtime state, evidence, approvals, and worker routing.
- Extended user intake to capture autonomy limits, risk tolerance, restore expectations, and target use-case category.

### Notes

- This release establishes the runtime architecture and control-surface model.
- Local worker routing is now explicit, but deeper Goose/Aider/Ollama transcript execution and richer preview pipelines remain future work.

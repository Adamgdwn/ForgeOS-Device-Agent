# Changelog

All notable changes to ForgeOS Device Agent will be documented in this file.

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

# ForgeOS Runtime-First Architecture

ForgeOS is a device rehabilitation agent with a GUI, not a GUI with some agent features.

## System Shape

- `app/core/orchestrator.py`
  Runtime entrypoint. Coordinates device sessions, tool execution, worker routing, approval gates, retry loops, and runtime plan emission.
- `app/core/runtime_workers.py`
  Explicit worker abstraction layer for `frontier_architect_worker`, `local_general_worker`, `local_editor_worker`, and `policy_guard`.
- `app/core/policy_guard.py`
  Deterministic safety gate for destructive actions and hard-stop classification.
- `app/core/runtime_planner.py`
  Converts raw tool outputs into a runtime session plan the GUI can display and the agent can audit.
- `app/tools/device_probe.py`
  Real device interrogation entrypoint. Starts from transport evidence and feeds the session.
- `app/tools/use_case_recommender.py`
  Best-use-case recommendation layer for turning hardware reality and user intent into a proposed device role.
- `app/tools/backup_restore.py`
  Pre-destructive backup capture and restore readiness planning.
- `app/tools/flash_executor.py`
  Install planning and gated execution path.
- `app/gui/control_app.py`
  Thin control surface for intake, evidence, approvals, restore readiness, worker routing, and runtime state.

## Runtime Flow

1. Intake and autonomy limits
2. Guided access enablement
3. Deep scan and assessment
4. Best-use-case recommendation
5. Backup and restore planning
6. Build and preview planning
7. Interactive verification
8. Install approval gate
9. Wipe and install
10. Post-install verification and completion

## Worker Routing Model

- `frontier_architect_worker`
  External premium reasoning path for architecture work, high-risk install planning, and escalations.
- `local_general_worker`
  Goose-backed local execution path for remediation loops, local tool use, and low-cost runtime work.
- `local_editor_worker`
  Aider-backed local repo editor for patching, fix loops, and session-local code changes.
- `policy_guard`
  Deterministic application logic for approvals, hard stops, and destructive boundaries.

## Runtime Artifacts

Each device session now includes:

- `runtime/session-plan.json`
- `runtime/worker-routing.json`
- `runtime/runtime-audit.json`

These artifacts make the runtime state explicit and UI-readable instead of burying decisions in scattered reports.

## Revised Repo Structure

```text
app/
  core/
    orchestrator.py
    runtime_workers.py
    policy_guard.py
    runtime_planner.py
    session_manager.py
    state_machine.py
  tools/
    device_probe.py
    use_case_recommender.py
    backup_restore.py
    flash_executor.py
  gui/
    control_app.py
devices/
  <device-session>/
    runtime/
      session-plan.json
      worker-routing.json
      runtime-audit.json
    reports/
    backup/
    restore/
    execution/
docs/
  runtime-architecture.md
  sprint-plan.md
```

# ForgeOS Runtime-First Architecture

ForgeOS is a device rehabilitation agent with a GUI, not a GUI with some agent features.

## System Shape

- `app/core/orchestrator.py`
  Runtime entrypoint. Coordinates device sessions, tool execution, worker routing, approval gates, retry loops, and runtime plan emission.
- `app/core/runtime_workers.py`
  Concrete worker runtime for `frontier_architect_worker`, `local_general_worker`, `local_editor_worker`, and `policy_guard`, including invocation, output capture, transcript logging, confidence scoring, retry telemetry, and escalation triggers.
- `app/core/host_capabilities.py`
  Host discovery layer for Goose, Aider, Ollama, `adb`, `fastboot`, emulator, and AVD readiness.
- `app/core/policy_guard.py`
  Deterministic safety gate for destructive actions and hard-stop classification.
- `app/core/runtime_planner.py`
  Converts raw tool outputs into a runtime session plan the GUI can display and the agent can audit.
- `app/core/runtime_pipelines.py`
  Executable preview and verification pipelines. These run real host-aware steps first, then fall back to simulated outputs when the host cannot support more.
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
  Goose-backed local execution path for remediation loops, local tool use, and low-cost runtime work. The runtime can also use Ollama directly for cheap local helper execution.
- `local_editor_worker`
  Aider-backed local repo editor for patching, fix loops, and session-local code changes. ForgeOS now supplies a practical Ollama-backed default model path where available.
- `policy_guard`
  Deterministic application logic for approvals, hard stops, and destructive boundaries.

## OEM Neutrality

- ForgeOS should start from generic Android transport and assessment logic, then add OEM-specific behavior only when live evidence matches that OEM.
- OEM-specific adapters such as Samsung download-mode support are extension paths, not the default runtime path.
- GUI guidance should come from resolved playbooks and runtime evidence, not hardcoded brand branches in application code.
- A device from another brand should still get a coherent session using the generic transport, recommendation, backup, preview, and verification layers even when no OEM-specific adapter exists yet.

## Runtime Artifacts

Each device session now includes:

- `runtime/session-plan.json`
- `runtime/worker-routing.json`
- `runtime/runtime-audit.json`
- `runtime/adapter-health.json`
- `runtime/preview/preview-execution.json`
- `runtime/verification/verification-execution.json`
- `runtime/workers/*.json`

These artifacts make the runtime state explicit and UI-readable instead of burying decisions in scattered reports.

## Revised Repo Structure

```text
app/
  core/
    orchestrator.py
    host_capabilities.py
    runtime_pipelines.py
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
      adapter-health.json
      session-plan.json
      worker-routing.json
      runtime-audit.json
      preview/
      verification/
      workers/
    reports/
    backup/
    restore/
    execution/
docs/
  runtime-architecture.md
  sprint-plan.md
  testing-checklist.md
```

## Current Execution Depth

- Worker routing is no longer just advisory. ForgeOS can run Goose, Aider, and Ollama-backed helper tasks through subprocess-backed adapters.
- Each worker execution records:
  - command
  - stdout/stderr
  - exit code
  - confidence
  - retry telemetry
  - escalation triggers
  - transcript path
- Preview now attempts real emulator and AVD discovery before falling back to a simulated walkthrough.
- Verification now runs real host-side and transport-aware checks, including `adb` probes when a device is reachable.

## Practical Limits

- Real execution depth still depends on host readiness.
- On a host without `adb`, `fastboot`, or emulator tooling, ForgeOS now records those capability gaps explicitly instead of pretending those pipelines are fully available.
- Aider depends on the local model or provider path being reachable. ForgeOS now defaults toward an Ollama-backed path when possible, but that still requires the Ollama service and configured model to be present.
- ForgeOS currently persists learned runtime knowledge under `knowledge/` and `promotion/`. That is useful for controlled learning, but it also means prior device-family sessions can influence later recommendations unless those learned artifacts are reset, isolated, or ignored for a clean test run.

## Clean-Run Expectation

- If you want a brand-agnostic validation run, treat the checked-in master data as seed data and the `knowledge/` plus `promotion/` directories as learned state.
- A truly clean run should either:
  - clear learned runtime knowledge before testing, or
  - route the session through an isolated test workspace, or
  - explicitly disable learned-family influence during evaluation.
- Until that isolation work lands in product code, ForgeOS should be described as OEM-capable but not yet guaranteed clean-room neutral across repeated mixed-brand sessions.

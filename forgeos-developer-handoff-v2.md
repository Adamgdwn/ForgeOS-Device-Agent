# ForgeOS Device Agent Developer Handoff v2

## Reading This Document

This handoff mixes two layers on purpose:

- current implemented reality in the repository
- target architectural direction for the next major phase

Treat it as a corrective roadmap, not as a claim that every subsystem described here already exists in full.

The safest way to use it is:

- preserve what is already working
- evolve components that are currently transitional
- use the target-state sections to guide the next refactor steps

## Project Intent

ForgeOS Device Agent is a Pop!_OS desktop-launchable autonomous Android device build agent.

Its intended end state is to:

1. detect a phone
2. identify the transport, trust, flashing, and recovery paths actually available
3. create or resume a per-device execution session from a reusable master framework
4. gather hardware, firmware, partition, and support facts directly from the device and host environment
5. infer or ask for only the minimum missing user constraints needed to proceed safely
6. choose the best attainable OS path for that exact hardware and policy context
7. generate and execute any missing code, adapters, configs, manifests, scripts, and tests required to continue
8. run build, sign, flash, validate, rollback-aware, and retry loops as autonomy allows
9. stop only for physical action, explicit destructive approval, missing external artifacts, or hard technical blockers

ForgeOS should not remain only a Codex handoff platform.
ForgeOS should evolve into an autonomous runtime that may use code generation internally as one of its execution capabilities.

## Project Identity

The system should be understood as:

- an event-driven runtime
- a hardware interrogation system
- a planning and blocker-resolution engine
- a code and configuration generation engine
- a build and validation engine
- a controlled learning and promotion framework
- a minimal operator monitor for visibility and approvals

The Pop!_OS launcher and GUI are supporting surfaces. They are not the center of the product.
The center of the product is the autonomous execution loop.

## Correct Mental Model

The project should be built around:

- `master/` = reusable autonomous build framework
- `devices/<device-session>/` = active device-specific execution workspace

Every attached device becomes an execution session.

The intended design direction is:

- ForgeOS orchestrates, persists, plans, generates, executes, validates, and retries
- the runtime uses code generation internally when adapters, configs, scripts, or strategy-specific logic are missing
- only proven reusable logic is promoted back into `master/`
- session folders are active execution workspaces, not static handoff bundles

## What The Current Build Got Right

The current scaffold already provides a useful base:

- Pop!_OS desktop launcher
- GUI application launch
- repo-local runtime with local `adb` and `fastboot`
- environment bootstrap
- background watchers for `adb`, `fastboot`, and USB-only Android-family devices
- per-device session creation under `devices/`
- persisted device/session artifacts
- explicit state machine
- controlled learning subsystem
- promotion-candidate subsystem
- autonomous non-destructive transport engagement attempts
- universal connection-engine planning
- strategy selection
- reporting and artifact generation

These are real assets and should be preserved where useful.

Recent additions that are already implemented:

- blocker classification and retry planning are active runtime components
- session-local codegen and patch-manifest registration now exist
- build-path resolution is persisted into session reports
- each session now gets a persisted `destructive-approval.json`
- each session now gets an `execution/flash-plan.json`
- the GUI now defaults to a simplified operator-monitor view with advanced details behind a toggle
- approved dry-run flash execution is wired end to end
- per-session backup bundles and restore plans are generated before destructive approval
- live `adb` hardware refresh is surfaced in the operator monitor when transport is available

## What Must Change

The core architectural issue is that the current design still leans too heavily toward preparing a session and handing the next implementation step to Codex.
That is no longer the target.

The new target is:

- ForgeOS itself continues after assessment
- ForgeOS itself classifies blockers
- ForgeOS itself generates the next missing code or config required to continue
- ForgeOS itself executes the next step and validates the outcome
- human interruption happens only when required by safety, physical interaction, policy, or unavailable artifacts

If ForgeOS hits a blocker that is software-solvable, it should attempt to solve it itself.
It should not default to writing a developer brief as the primary next action.

## Core Behavioral Rule

ForgeOS is not a guided workflow tool.
ForgeOS is an autonomous engineering agent.

Its job is not to stop at assessment and produce handoff documents.
Its job is to continue operating when it encounters a blocker by doing the following:

1. classify the blocker
2. determine whether the blocker can be solved by discovery, code generation, configuration generation, retry logic, strategy change, or human approval
3. if solvable by code or config, generate the required files immediately
4. integrate those files into the active device workspace
5. execute the next step
6. validate the result
7. update memory and continue

ForgeOS should ask the user only when:

- a destructive approval is required
- physical manipulation of the phone is required
- credentials, keys, or proprietary artifacts are unavailable
- a safety threshold is exceeded
- the device is genuinely blocked by hardware or trust-chain constraints

If a blocker is software-solvable, ForgeOS must attempt to solve it itself.

## Current Repo Areas

### App Runtime

- `app/main.py`
- `app/gui/control_app.py`

`app/main.py` currently bootstraps the environment, launches watchers, and starts the GUI.

This remains acceptable only if the GUI is repositioned as an operator monitor and approval surface.
It must not remain the conceptual center of the product.

### Core Orchestration

- `app/core/orchestrator.py`
- `app/core/session_manager.py`
- `app/core/state_machine.py`
- `app/core/bootstrap.py`

`orchestrator.py` should remain the main flow coordinator, but its mission must change.

At a high level it should move from:

1. probe device event
2. create/resume session
3. run feasibility assessment
4. run autonomous engagement
5. load user profile and OS goals
6. select strategy
7. build connection plan
8. generate Codex handoff files
9. update knowledge and promotion subsystems
10. write reports

To something closer to:

1. detect and fingerprint device
2. create or resume execution session
3. interrogate hardware, trust, transport, and partition state
4. synthesize confidence-scored device profile
5. classify support path and current blocker state
6. query master knowledge for reusable strategies and prior outcomes
7. choose the best attainable OS path
8. generate missing adapters, scripts, configs, manifests, and task files inside the active session
9. execute the next safe machine-solvable step
10. validate results
11. retry, patch, or shift strategy as needed
12. escalate only minimal required questions
13. write reports and promotion candidates

### Connection and Planning

- `app/core/connection_engine.py`
- `app/core/codex_handoff.py`

`connection_engine.py` can remain useful if it becomes part of a broader execution planner.

`codex_handoff.py` should no longer be treated as the final architectural endpoint.
It should evolve toward one or more of these roles:

- audit artifact exporter
- optional external review package generator
- debugging support tool

It should not represent the primary way ForgeOS moves forward.

At the current checkpoint, Codex handoff is already policy-demoted. The runtime can still emit handoff artifacts for audit or external review, but the intended center of gravity is the remediation loop inside the active session.

### Knowledge and Controlled Learning

- `app/core/knowledge.py`
- `app/core/promotion.py`
- `knowledge/`
- `promotion/`

This layer is still valid.
It should remain controlled rather than freeform self-rewriting.

It should continue to:

- record session outcomes
- track support confidence by device, vendor, and chipset families
- generate promotion candidates for review
- avoid silently rewriting destructive policy or security assumptions

What should change is that knowledge should also support active runtime decisions, not just retrospective summary.

### Device Engagement and Integration Boundaries

- `app/tools/autonomous_engagement.py`
- `app/tools/device_probe.py`
- `app/tools/feasibility_assessor.py`
- `app/tools/strategy_selector.py`
- `app/integrations/adb.py`
- `app/integrations/fastboot.py`
- `app/integrations/udev.py`

These modules should now feed an execution loop rather than a handoff flow.

Current boundaries still remain important:
ForgeOS should not pretend to bypass:

- locked screen approval
- disabled USB debugging
- OEM bootloader restrictions
- missing vendor transport
- trust-chain protections

But when a path is software-solvable, ForgeOS should actively generate and test the next implementation step rather than stopping at planning.

## Evolve “Codex Handoff” Into “Internal Codegen Runtime”

This is the single most important refactor.

Current idea:

- ForgeOS prepares a Codex-ready workspace and task brief
- Codex is then expected to generate missing device-specific logic

New idea:

- ForgeOS creates a device-specific execution workspace
- ForgeOS writes remediation artifacts directly into that workspace
- ForgeOS executes and inspects those artifacts as part of the normal runtime
- Codex handoff files become secondary exports only when useful

That shift is already partially underway in this repository through:

- `app/core/codegen_runtime.py`
- `app/core/patch_executor.py`
- `app/core/retry_planner.py`
- `app/core/blocker_engine.py`
- the expanded remediation states in `app/core/state_machine.py`

The next developer picking this up should preserve that direction and avoid re-centering the workflow around handoff generation or GUI guidance.
- ForgeOS invokes an internal code generation/runtime capability to generate missing device-specific logic
- ForgeOS writes those outputs directly into the session workspace
- ForgeOS then runs the next action, validates results, and iterates

External briefs may still be exported for debugging or human review, but they are not the main workflow.

This should be treated as an evolution path, not a requirement to immediately delete the current handoff system before the internal runtime exists.

## New Required Subsystems

Add these as first-class runtime components:

- `app/core/blocker_engine.py`
- `app/core/knowledge_lookup.py`
- `app/core/codegen_runtime.py`
- `app/core/patch_executor.py`
- `app/core/retry_planner.py`
- `app/tools/build_resolver.py`
- `app/integrations/oem_adapters/`

### Blocker Engine

The blocker engine should classify every roadblock into categories such as:

- `transport_blocker`
- `trust_blocker`
- `source_blocker`
- `build_blocker`
- `flash_blocker`
- `boot_blocker`
- `subsystem_blocker`
- `validation_blocker`
- `policy_blocker`
- `physical_action_blocker`

For every blocker, ForgeOS should produce:

- blocker type
- confidence
- whether it is machine-solvable
- required artifacts to attempt resolution
- planned next action
- retry budget
- escalation condition

Default policy:

- if machine-solvable, attempt resolution autonomously
- if not machine-solvable, ask one minimal question
- if unsafe, halt and preserve rollback path

### Knowledge Lookup

The runtime should actively query prior knowledge by:

- vendor family
- model family
- board family
- SoC family
- Android version family
- transport family
- previous session outcomes

This should influence path selection and code generation.

### Codegen Runtime

The codegen runtime should generate real files inside the active device session, including:

- adapter stubs
- scripts
- configs
- manifests
- validation plans
- parsing logic
- recovery workflows
- test drivers

This is not a documentation generator.
It is an execution support generator.

### Patch Executor

The patch executor should:

- apply generated files into the session workspace
- update state and reports
- queue next actions
- preserve checkpoints before impactful changes

### Retry Planner

The retry planner should decide whether to:

- retry the same action
- retry with modified transport or parameters
- switch build path
- fall back to a less ambitious but safer strategy
- escalate a question
- halt

### Build Resolver

The build resolver should choose among paths such as:

- hardened stock-derived path
- aftermarket ROM path
- GSI path
- custom device-specific path
- research-only path
- blocked path

It should base this on real evidence, not only heuristics.

### OEM Adapters

Create a dedicated area for OEM-specific transport or flashing logic, such as:

- Samsung download / Heimdall path
- recovery-specific flows
- vendor-specific restore logic

These must become real runtime-capable modules, not only ranked ideas in a plan.

## Updated State Machine

The state machine should be expanded to support autonomous continuation.

At minimum, add or formalize these states:

- `IDLE`
- `DEVICE_ATTACHED`
- `DISCOVER`
- `PROFILE_SYNTHESIS`
- `MATCH_MASTER`
- `BACKUP_PLAN`
- `PATH_SELECT`
- `BLOCKER_CLASSIFY`
- `CODEGEN_TASK`
- `PATCH_APPLY`
- `EXECUTE_STEP`
- `CONNECTIVITY_VALIDATE`
- `SECURITY_VALIDATE`
- `BRINGUP`
- `ITERATE`
- `QUESTION_GATE`
- `PROMOTE`
- `RESTORE`
- `BLOCKED`

Key behavior rules:

- every transition must be persisted
- after restart, resume from last safe state
- destructive operations remain dry-run by default until approval is captured
- connectivity and security validation happen before lower-priority expansion
- code generation and patch application are normal runtime actions, not exceptional ones

## User Profile and OS Goals

The existing `user-profile.json` and `os-goals.json` remain useful, but they must be demoted below hardware truth.

Correct priority order:

1. safety and reversibility
2. security
3. connectivity
4. core device operability
5. user goals and preference refinement
6. extended features

User intent matters only after the machine knows what the hardware can realistically support.

## What The GUI Is For Now

The GUI should be explicitly reframed as an operator monitor.

Its job is to:

- show current runtime objective
- show current blocker and whether it is machine-solvable
- show pending autonomous actions
- show pending approvals
- show current device session and artifact paths
- show confidence and risk honestly
- provide quick access to session files and logs

The GUI should not behave like a guided wizard.
It should not define the workflow.
The runtime defines the workflow.

Some guided language is still acceptable for operator safety and clarity, especially around approvals, physical-action blockers, and transport/trust issues.

Recommended UI language changes:

- “What To Do Now” -> `Current Objective`
- “Guided Workflow” -> `Agent Execution`
- “Helpful Files” -> `Artifacts`
- “Autonomous Actions” -> `Execution Queue`

## What A Typical Session Should Become

Using the Galaxy A5-style case, the intended flow should be:

1. USB watcher sees Samsung USB/MTP visibility
2. ForgeOS creates or resumes a device execution session
3. device profile is synthesized from USB, host, and any reachable Android facts
4. blocker engine classifies the state, for example as `transport_blocker`
5. knowledge lookup checks for Samsung-family, model-family, and adapter-family precedents
6. runtime decides whether the next best action is:
   - safe adb retry
   - Samsung download-mode research/adapter generation
   - transport-specific probe generation
   - research-only halt
7. if the problem is software-solvable, ForgeOS generates the next missing adapter, parser, script, or plan inside the session
8. ForgeOS executes that new step
9. results are validated and recorded
10. ForgeOS either continues, asks one minimal question, or halts honestly

The session should not terminate simply because a handoff package was written.

## Existing Tests

Current tests for bootstrap, session creation, transition persistence, learning engine, autonomous engagement, handoff generation, and strategy selection are useful and should be preserved while refactoring.

Preserve and expand testing around:

- blocker classification
- codegen runtime output
- patch application
- retry planning
- state persistence across autonomous iterations
- question gating
- build resolver decisions

Current verification baseline can remain:

- `python3 -m compileall app tests`
- `.venv/bin/pytest -q`

## Biggest Gaps

### 1. Real Device Intelligence

We still need a deeper hardware and support probe layer that can collect:

- exact model and codename
- SoC family
- slots and partitions
- radio and modem facts
- sensor and peripheral clues
- bootloader and trust-chain facts
- factory image and restore availability

### 2. OEM-Specific Adapters

The most useful immediate next real adapter remains:

- Samsung download / Heimdall path

This should become a true runtime-usable integration module rather than a planner-only candidate.

### 3. Build Resolver

We need a real resolver that chooses among:

- hardened stock-derived path
- aftermarket ROM path
- GSI path
- custom device-specific path
- research-only path
- blocked path

based on source availability, flashing reality, transport availability, and maintenance reality.

### 4. Wipe / Flash Approval Gate

This area is now partially implemented.

Already present:

- explicit wipe confirmation capture in the GUI
- rollback-path confirmation checkbox
- approval persistence in `destructive-approval.json`
- per-session flash plan generation in `execution/flash-plan.json`
- approved dry-run flash execution with audit transcript output
- policy blocking for live destructive execution by default

Still missing:

- true device-specific live flashing adapters
- restore fallback orchestration
- richer rollback disclosure and device-family restore intelligence
- post-flash validation and automatic restore-on-failure behavior

### 5. Validation Depth

We need real validation suites for:

- boot success
- charging
- storage health
- Wi-Fi
- Bluetooth
- modem/cellular
- camera
- audio
- OTA and rollback

## Refactor Priorities For The Next Coder

Proceed in this order:

1. stop treating Codex handoff as the primary architectural endpoint
2. add blocker classification and autonomous continuation states
3. embed internal code generation/runtime behavior into the execution loop
4. continue converting session folders from handoff-heavy packages into active execution workspaces
5. add knowledge-driven path matching for vendor/model/SoC families
6. implement the first true OEM-specific adapter, likely Samsung download / Heimdall
7. build the real build resolver
8. replace dry-run flash execution with real adapter-backed live execution where support is proven
9. add restore logic and deeper post-flash validation
10. preserve controlled promotion into `master/`

## Suggested Working Style

To stay aligned with project intent:

- keep `master/` generic and reusable
- put device-specific experiments in the session folder first
- prefer auditable files over hidden logic
- never assume all Android devices are equally supportable
- stop honestly on hard blockers
- treat code generation as an internal runtime capability
- preserve explicit policy boundaries around destructive behavior and security assumptions

## Useful Session Files To Inspect First

For any active phone session, start here:

- `device-profile.json`
- `session-state.json`
- `user-profile.json`
- `os-goals.json`
- `reports/assessment.json`
- `reports/engagement.json`
- `reports/blocker.json`
- `reports/build_plan.json`
- `reports/flash_plan.json`
- `reports/approval_gate.json`
- `reports/flash_execution.json`
- `plans/connection-plan.json`
- `execution/flash-plan.json`
- `destructive-approval.json`
- `codex/CODEX_TASK.md`
- `codex/codex-handoff.json`
- `codex/device-session.code-workspace`
- generated blocker reports
- generated runtime task files
- generated patch artifacts
- validation reports

Existing Codex export files currently remain useful because the repository still depends on them for real work. They should be treated as transitional but important artifacts until the internal runtime fully supersedes them.

## Bottom Line

This project should no longer be treated as only a launcher plus watcher plus Codex handoff scaffold.

It should now be treated as an autonomous device-session execution framework with:

- a working launcher
- an operator-monitor GUI
- autonomous non-destructive engagement
- controlled learning
- knowledge-guided strategy planning
- evolving blocker classification
- evolving internal code generation/runtime behavior
- active session workspaces
- explicit approval capture and approved dry-run destructive execution
- future live build/flash/validate loops under explicit approval and restore constraints

The next coder should refactor the current build into a self-continuing autonomous runtime while preserving the working session, GUI, planning, and handoff capabilities that already exist.

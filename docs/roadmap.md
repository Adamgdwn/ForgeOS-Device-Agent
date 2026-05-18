# ForgeOS Device Agent Roadmap

Last updated: 2026-05-18

## Purpose

This document is the compact project memory for future development sessions. Read it after `project-control.yaml` and before using older chat context or handoff notes.

ForgeOS Device Agent is intended to rescue and repurpose old Android phones and tablets by detecting the device, learning its exact hardware/software identity, asking only the useful missing questions, choosing the best attainable reuse path, and then executing as much of that path autonomously as governance and device safety allow.

## Current Governance

- Project status: active
- Risk tier: medium
- Governance level: 2 on the current 0 to 4 scale
- Agent autonomy: A1
- Sensitive data: yes
- Money movement: no
- Open exceptions: none recorded in `project-control.yaml`

Run the required preflight before substantial code or configuration work:

```bash
bash scripts/governance-preflight.sh
```

## Current State

The project is now a working desktop-launchable runtime with a GUI operator monitor, background device watchers, per-device sessions, deliberation artifacts, controlled runtime learning, and product/version memory.

Implemented runtime capabilities:

- Detects Android-family devices through ADB, Fastboot, and USB watcher paths.
- Creates or resumes per-device workspaces under `devices/`.
- Captures device identity, transport state, form factor, build details, and profile artifacts.
- Differentiates phone/tablet form factor using device facts plus an operator selector.
- Uses the current 0 to 4 governance scale through project controls.
- Runs a deliberation loop that writes current situation, action plan, lessons learned, and a decision journal under `runtime/thinking/`.
- Classifies blockers and distinguishes user-required, physical, artifact, policy, and machine-solvable conditions.
- Avoids treating tiny or simulated generated files as real flashable artifacts.
- Prevents local LLM/codegen output from being accepted as real upstream Android source artifacts.
- Produces session reports, recommendations, flash plans, backup/restore planning, and audit artifacts.
- Maintains durable product/version memory in `knowledge/product_memory.json`.
- Feeds product/version memory into planning and deliberation so similar devices can reuse prior lessons.
- Runs a deterministic starter troubleshooting loop before broad model-worker escalation, with learned product/version lessons able to augment the loop.
- Routes local models by task shape: fast triage prefers the lightweight installed helper model, while research, coding, and frontier-style reasoning use the configured reasoning model unless explicitly overridden.

Current live behavior on the active tablet path:

- The runtime can identify the attached Samsung tablet family and codename data when transport is available.
- It recognizes that no real flashable artifact has been proven for the observed version yet.
- It does not proceed into install planning without credible firmware/source artifacts or host build tooling.
- It asks focused next questions about staging real firmware/source or preparing host build tooling.

## Product And Version Memory

ForgeOS now records memory at two levels:

- Product memory: manufacturer, model, codename, form factors, observed sessions, reusable guidance, and support history.
- Version memory: Android version, build ID, fingerprint digest, blockers, strategies, artifacts, restore attempts, source history, and version-specific lessons.
- Identity normalization: weak early identities are merged into stronger compatible product records when a reliable codename proves they are the same device family. Equally specific related variants stay separate and are cross-linked.

Generated memory lives at:

```text
knowledge/product_memory.json
```

That file is intentionally ignored by git because it is runtime state. Future code should treat it as durable local knowledge, not source code.

Important next improvement: expand related-family lineage beyond codename matching, including regional variants, chipset families, and known aftermarket package compatibility.

Starter troubleshooting memory lives at:

```text
knowledge/starter_troubleshooting_memory.json
```

That file is intentionally ignored by git. It records which learned rules were applied for a product/version so future sessions can skip repeated broad model research and start from the proven checks.

## What Is Still Not Good Enough

ForgeOS is closer to the intended shape, but it is not yet the fully autonomous rescue agent.

Known gaps:

- It still cannot obtain proprietary firmware, bootloader unlock access, or device-specific aftermarket builds unless those are discoverable or supplied.
- The runtime can plan around missing Android build tooling, but it does not yet install or fully configure the Android source build environment by itself.
- Product memory now handles weak alias merging, but related-family lineage and compatibility inheritance are still basic.
- The starter troubleshooting loop can consume learned lessons, but its learned-rule vocabulary is still intentionally small.
- The GUI has been improved, but it is still an operator monitor layered on top of an evolving runtime rather than a polished product workflow.
- Deliberation is useful for planning and escalation, but it is not yet a deep multi-step executive that performs long-running investigation, validates alternate strategies, and tracks second/third-order consequences across days.
- Runtime learning records lessons, but promotion of reusable logic into `master/` still requires controlled review.
- Destructive operations remain intentionally gated by policy and approval.

## Near-Term Roadmap

1. Product memory normalization
   - Done: merge coarse and precise identities when a stronger compatible product identity is observed.
   - Done: cross-link equally specific related identities that share a reliable codename.
   - Next: track related models, regional variants, chipset families, and codenames with stronger evidence.
   - Prefer proven product/version lessons when selecting search terms and strategy paths.

2. Source and artifact acquisition loop
   - Build a governed artifact/source acquisition planner.
   - Track URLs, hashes, provenance, compatibility claims, and verification status.
   - Keep unverified artifacts out of install planning.

3. Host capability remediation
   - Add a machine-solvable host setup path for missing tools such as Android `repo`, build dependencies, and SDK/ADB utilities.
   - Keep installs explicit, logged, reversible where possible, and governed by policy.

4. Executive planning depth
   - Expand deliberation into a persistent goal stack with hypotheses, evidence, failed attempts, fallback paths, and consequence tracking.
   - Make repeated failures change strategy rather than simply repeat a blocker.
   - Keep a compact operator-facing explanation of what it is doing and why.
   - Promote repeated starter-loop lessons into reviewed reusable rules when they prove useful across sessions.
   - Add model-quality telemetry so model routes can be promoted, demoted, or made device-family-specific based on measured outcomes rather than preference.

5. Device conversation workflow
   - Ask the owner targeted questions about intended reuse: media kiosk, lightweight browser, smart display, camera monitor, local AI companion, offline notes, child-safe device, lab device, etc.
   - Translate those goals into OS, security, app, performance, and offline requirements.
   - Save those preferences per product/version and per session.

6. GUI operator monitor cleanup
   - Keep the first screen dense, useful, and stable.
   - Make current action, blocker, question, memory match, and next safe machine step immediately visible.
   - Avoid large empty panels and hidden scroll traps.

## Later Roadmap

- Build a promotion review workflow that turns repeated successful session-local fixes into reusable master capabilities.
- Add stronger artifact compatibility validation for partitions, boot images, recoveries, and ROM packages.
- Add device-family test fixtures that simulate common transport and support states.
- Add rollback drills and restore verification coverage.
- Expand local model integration for richer owner interviews and device reuse planning, while keeping safety controls outside model control.
- Add a release checklist that ties governance level, autonomy level, and destructive capability together.

## Resume Checklist

For a new development session:

1. Run `bash scripts/governance-preflight.sh`.
2. Read `project-control.yaml`.
3. Read this roadmap.
4. Inspect recent runtime state:

```bash
ls runtime/thinking
find devices -maxdepth 2 -type f | sort | tail -40
test -f knowledge/product_memory.json && jq '.products | keys' knowledge/product_memory.json
```

5. Check the app process and logs before assuming the runtime is idle.
6. Preserve generated runtime state unless cleanup is explicitly requested.

## Relationship To Older Handoff Notes

`forgeos-developer-handoff-v2.md` remains useful for the larger architectural direction, but this roadmap is the current short-form source of truth for where the implementation stands now.

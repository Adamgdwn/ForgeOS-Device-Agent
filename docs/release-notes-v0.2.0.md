# ForgeOS Device Agent v0.2.0

ForgeOS Device Agent now uses a runtime-first session model. This release moves the product closer to its intended shape as a device rehabilitation agent with a GUI, rather than a GUI-centered device tool.

## Highlights

- Explicit worker architecture for:
  - `frontier_architect_worker`
  - `local_general_worker`
  - `local_editor_worker`
  - `policy_guard`
- Runtime session planning artifacts for per-device execution state and auditability.
- Deterministic safety gating for destructive actions and restore readiness.
- Use-case recommendation for selecting the best attainable rehabilitation target per device.
- GUI updates that present runtime state, approvals, evidence, and worker routing as a control surface.

## Why This Matters

ForgeOS should be the runtime that rehabilitates a device, not just the interface around a script chain. This release makes the runtime model explicit in code, in the persisted session artifacts, and in the operator experience.

## Still Ahead

- Deeper device-family-specific flashing and restore adapters.
- More complete emulator-backed preview execution on hosts with Android SDK tooling installed.
- Stronger post-install verification suites and recovery rehearsal flows.
- Broader real-device flashing and restore coverage across Android device families.

# ForgeOS Testing Checklist

Use this checklist to validate the current execution-depth build on a real host.

## 1. Host Readiness

- Launch ForgeOS and confirm the Host Readiness panel reports:
  - `ADB`
  - `Fastboot`
  - `Goose`
  - `Aider`
  - `Ollama`
  - `Android emulator`
- If a capability is limited, confirm the UI says so explicitly instead of implying it is ready.

## 2. Clean-Run Guardrail

- Before using a different brand than the previous test device, decide whether this run should use prior learned knowledge or start clean.
- If you want a clean brand-agnostic test:
  - back up or clear `knowledge/session_outcomes.json`
  - back up or clear `knowledge/support_matrix.json`
  - back up or clear `promotion/candidates.json`
- Confirm the new session starts from generic transport guidance unless live device evidence resolves to a brand-specific playbook or OEM adapter.

## 3. Bootstrap Artifacts

- Confirm bootstrap writes a report under `output/`.
- Confirm the bootstrap payload includes `host_capabilities`.
- Confirm the reported local model matches the intended Ollama model.

## 4. Device Session Runtime Artifacts

After a device session is created, confirm the session contains:

- `runtime/session-plan.json`
- `runtime/worker-routing.json`
- `runtime/runtime-audit.json`
- `runtime/adapter-health.json`
- `runtime/preview/preview-execution.json`
- `runtime/verification/verification-execution.json`
- `runtime/workers/`

## 5. Worker Execution

- Confirm worker transcripts are created under `runtime/workers/`.
- Confirm each transcript records:
  - adapter name
  - command
  - stdout/stderr
  - exit code
  - confidence
  - retry telemetry
  - escalation triggers
- Confirm the GUI surfaces worker execution state, not just worker routing.

## 6. Preview Pipeline

- If emulator tooling and AVDs are installed:
  - confirm preview records emulator probe results
- If emulator tooling is missing:
  - confirm preview falls back to simulated mode
  - confirm the fallback reason is reflected in runtime artifacts

## 7. Verification Pipeline

- Confirm verification records host-side checks for:
  - `adb`
  - `fastboot`
  - backup bundle readiness
  - restore readiness
  - flash path readiness
- If a device is reachable over `adb`, confirm the verification pipeline records `getprop` and battery probe results.

## 8. OEM Neutrality Check

- Connect a non-Samsung test device if available and confirm:
  - the GUI does not mention Samsung-specific instructions unless the resolved playbook is actually Samsung-specific
  - the connection guidance is driven by the selected playbook steps
  - no install panel appears before recommendation, backup, preview, and verification readiness
  - a missing OEM adapter results in generic guidance and explicit limitations, not a broken flow

## 9. Local Editor Path

- Confirm Aider can run through the default local model path when Ollama is available.
- Confirm Aider-generated history/transcript files remain session-local and do not pollute the repo root.

## 10. Regression Check

Run:

```bash
./.venv/bin/python -m pytest -q
```

Expected result:

```text
31 passed
```

## 11. Honest Success Criteria

The build should be considered successful if:

- ForgeOS reports host capability gaps honestly
- worker execution is real and auditable
- preview and verification are executable pipelines rather than plan-only placeholders
- the runtime can continue autonomously where the host supports it
- true capability gaps are surfaced as explicit boundaries rather than hidden failures
- OEM-specific behavior activates only when supported by live evidence or an explicit playbook match
- prior learned device-family history is either intentionally used or intentionally excluded for the test run

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

## 2. Bootstrap Artifacts

- Confirm bootstrap writes a report under `output/`.
- Confirm the bootstrap payload includes `host_capabilities`.
- Confirm the reported local model matches the intended Ollama model.

## 3. Device Session Runtime Artifacts

After a device session is created, confirm the session contains:

- `runtime/session-plan.json`
- `runtime/worker-routing.json`
- `runtime/runtime-audit.json`
- `runtime/adapter-health.json`
- `runtime/preview/preview-execution.json`
- `runtime/verification/verification-execution.json`
- `runtime/workers/`

## 4. Worker Execution

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

## 5. Preview Pipeline

- If emulator tooling and AVDs are installed:
  - confirm preview records emulator probe results
- If emulator tooling is missing:
  - confirm preview falls back to simulated mode
  - confirm the fallback reason is reflected in runtime artifacts

## 6. Verification Pipeline

- Confirm verification records host-side checks for:
  - `adb`
  - `fastboot`
  - backup bundle readiness
  - restore readiness
  - flash path readiness
- If a device is reachable over `adb`, confirm the verification pipeline records `getprop` and battery probe results.

## 7. Local Editor Path

- Confirm Aider can run through the default local model path when Ollama is available.
- Confirm Aider-generated history/transcript files remain session-local and do not pollute the repo root.

## 8. Regression Check

Run:

```bash
./.venv/bin/python -m pytest -q
```

Expected result:

```text
31 passed
```

## 9. Honest Success Criteria

The build should be considered successful if:

- ForgeOS reports host capability gaps honestly
- worker execution is real and auditable
- preview and verification are executable pipelines rather than plan-only placeholders
- the runtime can continue autonomously where the host supports it
- true capability gaps are surfaced as explicit boundaries rather than hidden failures

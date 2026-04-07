# ForgeOS-Device-Agent — Codex Autonomous Improvement Instructions

> These instructions were generated from a full inspection of the repository and are
> intended for GitHub Copilot / Codex coding agent execution. Work the task list
> **top-to-bottom in priority order**. Each task includes exact file targets, the
> first-principles reasoning behind it, acceptance criteria, and hard constraints.
> Do not refactor code that is not listed. Do not rename public APIs. Every change
> must be tested by the existing test suite without modification to test files.

---

## Prime Directive

ForgeOS must behave like an autonomous agent that **keeps moving**. The agent may
only stop for two reasons:

1. A **physical action** is required from the operator (bootloader unlock button press, cable swap).
2. A **policy boundary** prevents the next action without explicit operator approval.

Everything else — unknown device, missing adapter, failed flash, stale research,
empty stub response — is a problem the agent must classify, plan around, and push
through using its own tools. "I don't know yet" is a research task, not a halt state.

---

## Task List (Priority Order)

---

### TASK 1 — Fix Silent Stub Pass-Through (CRITICAL)

**Why this matters:**
Every stub tool (`avb_signer`, `boot_validator`, `bootloader_manager`,
`hardening_engine`, `hardware_bringup`, `ota_tester`, `partition_mapper`,
`source_resolver`) currently returns `{"status": "stub"}` with no error flag. The
orchestrator and blocker engine treat this as a successful result. The agent silently
progresses past critical validation steps without doing any work. This is a
correctness hole — the agent believes it has signed images, validated boot, and
mapped partitions when it has not.

**Files to change:**
- `app/tools/avb_signer.py`
- `app/tools/boot_validator.py`
- `app/tools/bootloader_manager.py`
- `app/tools/hardening_engine.py`
- `app/tools/hardware_bringup.py`
- `app/tools/ota_tester.py`
- `app/tools/partition_mapper.py`
- `app/tools/source_resolver.py`

**What to implement in each stub:**

Replace each `run()` stub body with this pattern (adapt field names to the tool's
`output_schema`):

```python
def run(self, payload: dict[str, object]) -> dict[str, object]:
    return {
        # mirror every output_schema key with a safe empty/default value
        "<primary_output_key>": [],
        "status": "not_implemented",
        "blocks": True,
        "reason": (
            f"{self.name} is not yet implemented. "
            "The blocker engine will classify this as a machine_solvable codegen task."
        ),
    }
```

**Priority order for full implementation** (implement in this sequence — each one
unblocks the next pipeline stage):

1. **`partition_mapper.py`** — reads `adb shell cat /proc/partitions` and
   `/proc/mounts`, returns a structured dict of partition name → size/mount/type.
   Use `subprocess` via the existing `adb_runner` pattern already in
   `DeviceProbeTool`. No network calls required. Output schema:
   `{"partitions": [{"name": str, "size_kb": int, "mount": str, "type": str}], "status": "ok"}`.

2. **`bootloader_manager.py`** — wraps `fastboot oem unlock` / `fastboot flashing
   unlock` dispatch. Must check `policy.allow_live_destructive_actions` before
   issuing any unlock command. If policy disallows it, return
   `{"status": "awaiting_policy_approval", "blocks": True}`. Output schema:
   `{"unlock_issued": bool, "status": str}`.

3. **`boot_validator.py`** — after a flash, runs `adb shell getprop
   ro.boot.verifiedbootstate` and `adb shell getprop ro.boot.flash.locked`. Returns
   pass/fail with values. Output schema:
   `{"verified_boot_state": str, "bootloader_locked": bool, "status": "pass"|"fail"}`.

4. **`avb_signer.py`** — calls `avbtool` if available on `PATH`, otherwise returns
   `{"status": "avbtool_missing", "blocks": False, "signed_artifacts": []}` (non-
   blocking — unsigned test keys are acceptable for development builds). Do not
   shell out to anything not on PATH; check `shutil.which("avbtool")` first.

5. **`source_resolver.py`** — see TASK 3 below for full spec.

6. **`hardware_bringup.py`**, **`hardening_engine.py`**, **`ota_tester.py`** — these
   are later-pipeline tools. Implement the safe empty-return pattern from above so
   they don't silently pass, but defer full implementation after tasks 1–3 are done.

**Acceptance criteria:**
- `grep -r '"status": "stub"' app/tools/` returns zero results.
- Blocker engine can receive `blocks: True` from a stub and correctly classifies it
  as `source_blocker` or `codegen_task` rather than passing through.

---

### TASK 2 — Add Retry Heat Tracking to RetryPlanner (STRUCTURAL)

**Why this matters:**
`RetryPlanner.build_plan()` currently evaluates only the current blocker with no
memory of prior attempts. The agent can loop on the same `machine_solvable` path
indefinitely because nothing detects "we have tried this exact remediation 4 times
and not advanced." This is the root cause of the `ITERATE` dead-end loop.

**File to change:** `app/core/retry_planner.py`

**What to implement:**

Add a `_heat_file(session_dir)` helper that reads/writes
`session_dir/reports/retry-heat.json`. Schema:

```json
{
  "cycles": [
    {
      "timestamp": "<iso8601>",
      "blocker_type": "<str>",
      "action_taken": "<str>",
      "advanced": false
    }
  ]
}
```

Modify `build_plan()` signature to accept an optional `session_dir: Path | None = None`
parameter. When `session_dir` is provided:

1. Load the heat file (or start empty).
2. Count consecutive cycles where `blocker_type` matches the current blocker AND
   `advanced == False`. Call this `stall_count`.
3. If `stall_count >= 3` and `machine_solvable == True`, override `action` to
   `"escalate_strategy"` and set `rationale` to explain the stall.
4. If `stall_count >= 5`, override `action` to `"halt_and_review"` regardless of
   `machine_solvable`.
5. Append the current cycle record to the heat file with `advanced = False` (the
   orchestrator will update it to `True` after a successful cycle via a new
   `RetryPlanner.mark_advanced(session_dir)` method you must also add).

Add `mark_advanced(self, session_dir: Path) -> None` — sets the last heat record's
`advanced` to `True` and rewrites the file.

**Acceptance criteria:**
- Unit test: build a heat file with 3 consecutive `machine_solvable=True, advanced=False`
  entries, call `build_plan()` — assert action is `"escalate_strategy"`.
- Unit test: 5 consecutive stalled entries → action is `"halt_and_review"`.

---

### TASK 3 — Implement source_resolver with Download + TTL (CRITICAL)

**Why this matters:**
The research worker fetches community knowledge but the agent has no path from
"XDA thread found" to "firmware file available locally." The `source_blocker` is
the most common reason new devices never reach `FLASH_PREP`. Additionally, research
results are cached forever — a device that had a LineageOS port that was later
abandoned will keep presenting a stale recommendation.

**File to change:** `app/tools/source_resolver.py`
**New file:** `app/tools/_source_cache.py` (internal helper, not a tool)

**What to implement in `source_resolver.py`:**

`SourceResolverTool.run(payload)` receives:
```python
{
    "session_dir": str,
    "manufacturer": str,
    "model": str,
    "device_codename": str,
    "research_path": str,   # path to device_community.json
    "target_os": str,       # e.g. "lineageos", "grapheneos", "calyx"
}
```

Steps:
1. Load `device_community.json` if it exists. Check `fetched_at` field — if older
   than 30 days (`SOURCE_CACHE_TTL_DAYS = 30`), set `stale = True` and return
   `{"status": "stale_research", "blocks": True, "stale": True}` so the research
   worker re-fires.
2. Extract the first URL-shaped string from the `download_hints` list in the
   research JSON (field added by research worker). If none found, return
   `{"status": "no_source_found", "blocks": True}`.
3. Use `urllib.request.urlretrieve` (stdlib only — no new dependencies) to fetch
   the file into `session_dir / "downloads" / <filename>`. Stream in 8 MB chunks.
   If the download fails or the URL is a non-direct link (no file extension in
   path), return `{"status": "download_failed", "blocks": True, "url": url}`.
4. Verify the downloaded file is > 10 MB (sanity check — firmware images are never
   tiny). If not, delete and return `{"status": "bad_download", "blocks": True}`.
5. Return `{"status": "ok", "blocks": False, "local_path": str(path), "source_url": url}`.

**TTL logic in `_source_cache.py`:**

```python
SOURCE_CACHE_TTL_DAYS = 30

def is_stale(research_path: Path) -> bool:
    """Return True if research file is missing or older than TTL."""
    ...

def touch_fetched_at(research_path: Path) -> None:
    """Update fetched_at to now without changing other fields."""
    ...
```

**Acceptance criteria:**
- Calling `run()` with a research file that has `fetched_at` > 30 days ago returns
  `status: stale_research`.
- Calling `run()` with a fresh research file and a reachable direct URL downloads
  the file and returns `status: ok`.
- No new third-party packages — stdlib only.

---

### TASK 4 — Fix ITERATE Dead-End: Add DEEP_SCAN Escalation (STRUCTURAL)

**Why this matters:**
When `_run_runtime_cycle` produces no install candidate and no machine-solvable
blocker, the state machine lands in `ITERATE`. The `ITERATE` → `BLOCKER_CLASSIFY`
→ same result loop is already allowed by the state machine [see `ALLOWED_TRANSITIONS`
in `state_machine.py`]. But nothing in the orchestrator detects consecutive `ITERATE`
landings and escalates to `DEEP_SCAN`, which re-probes the device. The agent just
loops.

**Files to change:**
- `app/core/orchestrator.py`
- `app/core/state_machine.py`

**What to implement:**

In `state_machine.py`, add `ITERATE → DEEP_SCAN` to `ALLOWED_TRANSITIONS`:
```python
SessionStateName.ITERATE: {
    SessionStateName.BLOCKER_CLASSIFY,
    SessionStateName.PATH_SELECT,
    SessionStateName.DEEP_SCAN,   # ← add this
    SessionStateName.BLOCKED,
},
```

In `orchestrator.py`, at the end of `_run_runtime_cycle()` where the state is
evaluated after `inspection`:

1. Load the session state's `iterate_count` field (add this field to
   `SessionState` model if absent, default `0`).
2. If the current landing state is `ITERATE`, increment `iterate_count` and save.
3. If `iterate_count >= 2`, call `_safe_transition(session_dir, "DEEP_SCAN",
   "Consecutive ITERATE cycles detected — forcing device re-probe")`  and reset
   `iterate_count` to 0.
4. In `DEEP_SCAN` handling, force a fresh `device_probe.execute()` call and update
   the session profile — do not use cached profile data.

**Acceptance criteria:**
- Two consecutive `ITERATE` landings (no install candidate, no machine-solvable
  blocker) must produce a `DEEP_SCAN` transition in the session log.
- A `DEEP_SCAN` transition must produce a fresh `getprop`-level device probe result
  that overwrites the cached profile.

---

### TASK 5 — Fix Strategy Not Updating After Remediation (STRUCTURAL)

**Why this matters:**
After `INSPECT_RESULT`, the blocker is re-classified. If codegen resolved a
transport blocker (e.g., wrote a new ADB wrapper that changed `transport` from
`usb-unknown` to `usb-adb`), `selected_strategy` still points to the pre-
remediation strategy. The build plan will use the wrong flash path.

**File to change:** `app/core/orchestrator.py`

**Where:** In `_run_runtime_cycle()`, after `inspection` is produced and blocker is
re-classified.

**What to implement:**

After the re-classification block, add:

```python
# If remediation changed the effective transport or support_status, re-evaluate strategy.
new_support = new_blocker.get("support_status") or assessment.get("support_status")
if new_support and new_support != current_state.support_status.value:
    updated_strategy = self.strategy_selector.execute({
        "assessment": {**assessment, "support_status": new_support},
        "device": device_payload,
        "user_profile": { ... },   # same dict as used in handle_device_event
        "os_goals": { ... },
    })
    current_state = replace(current_state, selected_strategy=updated_strategy["strategy_id"])
    self.sessions.write_session_state(session_dir, current_state)
    self.logger.info(
        "Strategy updated after remediation: %s → %s",
        old_strategy,
        updated_strategy["strategy_id"],
    )
```

**Acceptance criteria:**
- A session where remediation changes `support_status` from `partial` to `supported`
  must record the new `selected_strategy` in the session state JSON.

---

### TASK 6 — Add QUESTION_GATE Re-trigger on Device State Change (AUTONOMY)

**Why this matters:**
If the operator plugs in a USB cable or changes the device to fastboot mode while
the session is in `QUESTION_GATE`, nothing happens. The agent waits indefinitely.
The watcher fires a new USB event but the orchestrator creates a new session instead
of resuming the waiting one.

**Files to change:**
- `app/core/orchestrator.py` — `handle_device_event()`
- Any watcher in `app/watchers/` that dispatches device attachment events

**What to implement:**

In `handle_device_event()`, before `sessions.create_or_resume()`:

1. Check if any existing session for the same device serial is in `QUESTION_GATE`
   state: `existing = self.sessions.find_waiting_session(probe_result["device"]["serial"])`.
2. If found, call `_safe_transition(existing, "BLOCKER_CLASSIFY", "Device state changed while waiting at QUESTION_GATE — re-entering blocker classification")` and then call `recompute_session_runtime(existing)` instead of starting a new session.
3. Add `SessionManager.find_waiting_session(serial: str) -> Path | None` that scans
   `devices/*/session-state.json` for `state == "QUESTION_GATE"` and matching serial.

**Acceptance criteria:**
- A session in `QUESTION_GATE` for serial `ABC123` — when a new USB event fires for
  `ABC123` — must resume the existing session rather than creating a new one.

---

### TASK 7 — Add Knowledge Deprecation to PromotionEngine (KNOWLEDGE INTEGRITY)

**Why this matters:**
Adapters are promoted to `master/` and never removed. A bad adapter (promoted before
real device evidence, or promoted from `probe_no_device` auto-pass) builds false
confidence in the knowledge base. Over time, every device will appear "supported"
whether it is or not.

**File to change:** `app/core/promotion.py`

**What to implement:**

Add `deprecate_adapter(self, family_key: str, reason: str) -> None`:

1. Moves `master/adapters/<family_key>/` to
   `master/adapters/_deprecated/<family_key>_<timestamp>/`.
2. Writes a `deprecation.json` alongside:
   ```json
   {"deprecated_at": "<iso8601>", "reason": "<str>", "family_key": "<str>"}
   ```
3. Updates the support matrix to remove the family_key entry and marks it as
   `"deprecated"` so it can be rebuilt from scratch on next session.

Add `audit_promoted_adapters(self) -> list[str]` that returns family keys where:
- The adapter was promoted from a `probe_no_device` test result (detectable from
  the `meta.json` `test_source` field, if present), AND
- No real-device session has since confirmed the adapter.

Call `audit_promoted_adapters()` from `handle_device_event()` at startup (once per
run, not once per cycle) and log a warning for each flagged adapter.

**Acceptance criteria:**
- Calling `deprecate_adapter("google_pixel_6")` moves the adapter directory and
  writes `deprecation.json`.
- `audit_promoted_adapters()` returns family keys that match the `probe_no_device`
  origin condition.

---

## Hard Constraints for All Tasks

1. **No new third-party packages.** Use stdlib (`pathlib`, `subprocess`, `json`,
   `urllib.request`, `shutil`, `dataclasses`) and packages already in
   `requirements.txt`. Do not add entries to `requirements.txt`.

2. **Policy guard is non-negotiable.** Any tool that issues a destructive command
   (`fastboot oem unlock`, `fastboot flash`, `adb reboot bootloader`) MUST check
   `policy.allow_live_destructive_actions` before executing. If the policy disallows
   it, return a structured `blocks: True` result and do not shell out.

3. **No monkey-patching of `state_machine.py` transitions.** Only add transitions
   that are listed in these instructions. Do not remove any existing transition.

4. **All subprocess calls use `timeout=`.**  Every `subprocess.run()` or
   `subprocess.Popen()` must specify a `timeout` (recommend 30 seconds for ADB
   commands, 120 seconds for fastboot flash). Unconstrained shell calls are a
   reliability hole.

5. **Session state writes are atomic.** Use a write-then-rename pattern
   (`path.with_suffix(".tmp")` → `path.rename(target)`) for all session state JSON
   writes to prevent corruption from mid-write interrupts.

6. **No silent exceptions.** Every `except Exception` block must log the exception
   at `WARNING` or higher before returning a structured error dict. Do not swallow.

7. **Tests must pass.** Run `pytest` after each task. Do not skip or modify existing
   test files. Add new test files only (e.g., `tests/test_retry_planner_heat.py`).

---

## Verification Order

After completing all tasks, verify this end-to-end sequence works without human
intervention for a device that has no master adapter:

```
IDLE → DEVICE_ATTACHED → DISCOVER → PROFILE_SYNTHESIS → ASSESS
     → MATCH_MASTER → BACKUP_PLAN → PATH_SELECT → BLOCKER_CLASSIFY
     → CODEGEN_TASK → CODEGEN_WRITE → PATCH_APPLY → EXECUTE_ARTIFACT
     → INSPECT_RESULT → BLOCKER_CLASSIFY (re-classify)
     → BUILD_DEVICE → SIGN_IMAGES → FLASH_PREP → INSTALL_APPROVAL
```

The sequence must not land in `QUESTION_GATE` unless a physical action is required.
It must not loop more than twice at `ITERATE` without escalating to `DEEP_SCAN`.
It must not pass through any stub tool without producing a `blocks: True` result
that the blocker engine classifies.

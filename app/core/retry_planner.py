from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import utc_now


class RetryPlanner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _heat_file(self, session_dir: Path) -> Path:
        return session_dir / "reports" / "retry-heat.json"

    def _load_heat(self, session_dir: Path) -> dict[str, Any]:
        path = self._heat_file(session_dir)
        if not path.exists():
            return {"cycles": []}
        try:
            payload = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            return {"cycles": []}
        return payload if isinstance(payload, dict) else {"cycles": []}

    def _write_heat(self, session_dir: Path, payload: dict[str, Any]) -> None:
        path = self._heat_file(session_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

    def build_plan(
        self,
        blocker: dict[str, Any],
        generated: dict[str, Any] | None = None,
        worker_self_heal: dict[str, Any] | None = None,
        session_dir: Path | None = None,
    ) -> dict[str, Any]:
        machine_solvable = blocker.get("machine_solvable", False)
        blocker_type = blocker.get("blocker_type")
        if blocker_type == "none":
            action = "return_to_main_plan"
            rationale = "The current blocker has been resolved enough for the runtime to continue the main execution path."
        elif machine_solvable:
            action = "continue_autonomous_remediation"
            rationale = "The blocker is machine-solvable, so the runtime should generate, execute, inspect, and reclassify before asking for help."
        elif blocker_type in {"trust_blocker", "physical_action_blocker"}:
            action = "await_user_action"
            rationale = "The next action depends on physical interaction or on-device approval."
        else:
            action = "halt_and_review"
            rationale = "The blocker is not safely solvable by autonomous retry."

        if session_dir is not None:
            heat = self._load_heat(session_dir)
            cycles = list(heat.get("cycles") or [])
            stall_count = 0
            for cycle in reversed(cycles):
                if cycle.get("blocker_type") != blocker_type or cycle.get("advanced") is True:
                    break
                stall_count += 1
            if stall_count >= 5:
                action = "halt_and_review"
                rationale = "The runtime stalled on the same blocker for five consecutive cycles and must stop for review."
            elif stall_count >= 3 and machine_solvable:
                action = "escalate_strategy"
                rationale = "The runtime stalled on the same machine-solvable blocker for three consecutive cycles and should escalate strategy."
            cycles.append(
                {
                    "timestamp": utc_now(),
                    "blocker_type": blocker_type,
                    "action_taken": action,
                    "advanced": False,
                }
            )
            self._write_heat(session_dir, {"cycles": cycles})

        return {
            "generated_at": utc_now(),
            "action": action,
            "rationale": rationale,
            "retry_budget": blocker.get("retry_budget", 0),
            "generated_files": (generated or {}).get("generated_files", []),
            "worker_self_heal": worker_self_heal or {},
        }

    def mark_advanced(self, session_dir: Path) -> None:
        heat = self._load_heat(session_dir)
        cycles = list(heat.get("cycles") or [])
        if not cycles:
            return
        cycles[-1]["advanced"] = True
        self._write_heat(session_dir, {"cycles": cycles})

    def write(self, session_dir: Path, payload: dict[str, Any]) -> Path:
        path = session_dir / "reports" / "retry-plan.json"
        path.write_text(json.dumps(payload, indent=2))
        return path

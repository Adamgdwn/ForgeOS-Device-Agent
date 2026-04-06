from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import utc_now


class RetryPlanner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def build_plan(
        self,
        blocker: dict[str, Any],
        generated: dict[str, Any] | None = None,
        worker_self_heal: dict[str, Any] | None = None,
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

        return {
            "generated_at": utc_now(),
            "action": action,
            "rationale": rationale,
            "retry_budget": blocker.get("retry_budget", 0),
            "generated_files": (generated or {}).get("generated_files", []),
            "worker_self_heal": worker_self_heal or {},
        }

    def write(self, session_dir: Path, payload: dict[str, Any]) -> Path:
        path = session_dir / "reports" / "retry-plan.json"
        path.write_text(json.dumps(payload, indent=2))
        return path

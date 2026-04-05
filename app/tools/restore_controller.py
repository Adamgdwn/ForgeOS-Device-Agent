from __future__ import annotations

import json
from pathlib import Path

from app.tools.base import BaseTool


class RestoreControllerTool(BaseTool):
    name = "restore_controller"
    input_schema = {"session_dir": "string", "backup_plan": "object"}
    output_schema = {"status": "string", "summary": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        session_dir = Path(str(payload["session_dir"]))
        backup_plan = dict(payload["backup_plan"])
        restore_dir = session_dir / "restore"
        restore_dir.mkdir(parents=True, exist_ok=True)

        plan = {
            "status": "planned",
            "summary": "Prepared a restore plan from the captured backup evidence.",
            "backup_bundle_path": backup_plan.get("backup_bundle_path", ""),
            "metadata_backup_path": backup_plan.get("metadata_backup_path", ""),
            "steps": [
                "Open the session recovery bundle and inspect the saved device and session metadata.",
                "Use the recorded flash plan, blocker report, and connection plan to choose the safest reinstall path.",
                "If adb metadata was captured, replay settings and package evidence only after the device is stable.",
                "If vendor factory images are unavailable, stop and escalate instead of guessing a restore path."
            ],
            "limitations": backup_plan.get("limitations", []),
        }
        restore_plan_path = restore_dir / "restore-plan.json"
        restore_plan_path.write_text(json.dumps(plan, indent=2))
        return {
            "status": "planned",
            "summary": plan["summary"],
            "restore_plan_path": str(restore_plan_path),
            "details": plan,
        }

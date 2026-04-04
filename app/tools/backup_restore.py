from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class BackupAndRestorePlannerTool(BaseTool):
    name = "backup_and_restore_planner"
    input_schema = {"device": "object"}
    output_schema = {"restore_path_feasible": "boolean", "plan": "object"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "restore_path_feasible": False,
            "plan": {
                "status": "stub",
                "notes": "Implement factory image lookup and partition-safe backup planning.",
            },
        }

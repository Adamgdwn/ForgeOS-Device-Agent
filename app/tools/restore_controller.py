from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class RestoreControllerTool(BaseTool):
    name = "restore_controller"
    input_schema = {"device": "object", "plan": "object"}
    output_schema = {"status": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {"status": "stub"}

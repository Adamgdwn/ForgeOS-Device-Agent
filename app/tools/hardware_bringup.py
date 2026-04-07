from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class HardwareBringupTesterTool(BaseTool):
    name = "hardware_bringup_tester"
    input_schema = {"device": "object"}
    output_schema = {"status": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "status": "not_implemented",
            "blocks": True,
            "reason": "hardware_bringup_tester is not implemented yet.",
        }

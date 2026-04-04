from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class FlashExecutorTool(BaseTool):
    name = "flash_executor"
    input_schema = {"signed_artifacts": "array", "device": "object"}
    output_schema = {"status": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {"status": "stub"}

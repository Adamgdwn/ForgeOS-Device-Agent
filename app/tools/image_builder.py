from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class ImageBuilderTool(BaseTool):
    name = "image_builder"
    input_schema = {"strategy_id": "string", "device": "object"}
    output_schema = {"artifacts": "array"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {"artifacts": [], "status": "stub"}

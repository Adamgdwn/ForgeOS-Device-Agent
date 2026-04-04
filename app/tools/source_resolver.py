from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class SourceResolverTool(BaseTool):
    name = "source_resolver"
    input_schema = {"strategy_id": "string"}
    output_schema = {"sources": "array"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {"sources": [], "status": "stub"}

from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class PartitionMapperTool(BaseTool):
    name = "partition_mapper"
    input_schema = {"device": "object"}
    output_schema = {"partitions": "array"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {"partitions": [], "status": "stub"}

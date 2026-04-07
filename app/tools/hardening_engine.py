from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class HardeningEngineTool(BaseTool):
    name = "hardening_engine"
    input_schema = {"device": "object", "strategy_id": "string"}
    output_schema = {"status": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "status": "not_implemented",
            "blocks": True,
            "reason": "hardening_engine is not implemented yet.",
        }

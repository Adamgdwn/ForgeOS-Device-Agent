from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class BuildStrategySelectorTool(BaseTool):
    name = "build_strategy_selector"
    input_schema = {"assessment": "object", "device": "object"}
    output_schema = {"strategy_id": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        assessment = dict(payload["assessment"])
        if assessment.get("support_status") == "actionable":
            return {
                "strategy_id": assessment.get("recommended_path", "hardened_existing_os"),
                "reason": "Prefer maintainable hardened path before novel device-specific rebuilds.",
            }
        return {
            "strategy_id": "research_only",
            "reason": "Support feasibility is not proven enough for destructive build flow.",
        }

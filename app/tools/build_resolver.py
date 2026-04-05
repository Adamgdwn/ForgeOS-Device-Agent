from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class BuildResolverTool(BaseTool):
    name = "build_resolver"
    input_schema = {
        "assessment": "object",
        "connection_plan": "object",
        "selected_strategy": "string",
        "user_profile": "object",
        "os_goals": "object",
    }
    output_schema = {"os_path": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        assessment = dict(payload.get("assessment", {}))
        connection_plan = dict(payload.get("connection_plan", {}))
        selected_strategy = str(payload.get("selected_strategy", "research_only"))
        user_profile = dict(payload.get("user_profile", {}))

        if assessment.get("support_status") == "blocked":
            return {
                "os_path": "blocked_path",
                "reason": "The device is blocked by support or safety constraints.",
            }

        if selected_strategy in {"transport_recovery", "research_only", "blocked_research"}:
            return {
                "os_path": "research_only_path",
                "reason": "A manageable transport and support baseline must exist before a build path can be chosen.",
            }

        if selected_strategy == "hardened_stock":
            return {
                "os_path": "hardened_stock_path",
                "reason": "Profile and support evidence favor a stock-derived, maintainable path.",
            }

        if selected_strategy in {"aftermarket_rom", "privacy_hardened_aftermarket"}:
            return {
                "os_path": "aftermarket_path",
                "reason": "The selected strategy favors an aftermarket or privacy-hardened path where support allows it.",
            }

        if selected_strategy == "managed_family_build":
            return {
                "os_path": "managed_family_path",
                "reason": "The intended user profile favors a constrained, family-oriented build.",
            }

        if selected_strategy == "device_specific_build":
            return {
                "os_path": "device_specific_path",
                "reason": "The selected strategy favors device-specific tuning and deeper customization.",
            }

        return {
            "os_path": "maintainable_hardened_path",
            "reason": "Default to the most maintainable hardened path while preserving room for later refinement.",
        }

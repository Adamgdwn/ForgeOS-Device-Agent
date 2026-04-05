from __future__ import annotations

from pathlib import Path

from app.core.models import GoogleServicesPreference, PriorityFocus, TechnicalComfort, UserPersona
from app.tools.base import BaseTool


class BuildStrategySelectorTool(BaseTool):
    name = "build_strategy_selector"
    input_schema = {
        "assessment": "object",
        "device": "object",
        "user_profile": "object",
        "os_goals": "object",
    }
    output_schema = {"strategy_id": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        assessment = dict(payload["assessment"])
        user_profile = dict(payload.get("user_profile", {}))
        os_goals = dict(payload.get("os_goals", {}))
        support_status = assessment.get("support_status")
        recommended_path = assessment.get("recommended_path", "research_only")
        persona = user_profile.get("persona", UserPersona.DAILY.value)
        comfort = user_profile.get("technical_comfort", TechnicalComfort.LOW.value)
        primary_priority = user_profile.get("primary_priority", PriorityFocus.SECURITY.value)
        google_pref = user_profile.get(
            "google_services_preference",
            GoogleServicesPreference.KEEP.value,
        )
        top_goal = os_goals.get("top_goal", primary_priority)

        if support_status == "blocked":
            return {
                "strategy_id": "blocked_research",
                "reason": "The device is blocked by transport or restore-path feasibility and should not proceed.",
            }

        if recommended_path == "transport_engagement":
            return {
                "strategy_id": "transport_recovery",
                "reason": "The first priority is to reach adb, fastboot, or recovery transport before OS selection.",
            }

        if support_status != "actionable":
            return {
                "strategy_id": "research_only",
                "reason": "Support feasibility is not proven enough for destructive build flow.",
            }

        if persona == UserPersona.SENIOR.value or top_goal == PriorityFocus.SIMPLICITY.value:
            return {
                "strategy_id": "hardened_stock",
                "reason": "Prioritize stability, familiarity, and supportable defaults for a simple user experience.",
            }

        if persona == UserPersona.CHILD.value:
            return {
                "strategy_id": "managed_family_build",
                "reason": "Prioritize constrained usage, safety defaults, and durability over experimentation.",
            }

        if persona == UserPersona.DEVELOPER.value and comfort == TechnicalComfort.HIGH.value:
            return {
                "strategy_id": "aftermarket_rom",
                "reason": "Developer profile favors unlockable, maintainable, and modifiable aftermarket paths when actionable.",
            }

        if persona == UserPersona.PRIVACY.value or google_pref == GoogleServicesPreference.REMOVE.value:
            return {
                "strategy_id": "privacy_hardened_aftermarket",
                "reason": "Privacy-focused profile favors reduced Google dependency and stronger hardening where support allows it.",
            }

        if top_goal == PriorityFocus.BATTERY.value:
            return {
                "strategy_id": "hardened_stock",
                "reason": "Battery-focused profile usually benefits from the most maintainable and hardware-tuned base path.",
            }

        if top_goal == PriorityFocus.PERFORMANCE.value:
            return {
                "strategy_id": "device_specific_build",
                "reason": "Performance-focused profile may justify deeper device-specific tuning when support is actionable.",
            }

        return {
            "strategy_id": "hardened_existing_os",
            "reason": "Prefer the most maintainable hardened path before novel device-specific rebuilds.",
        }

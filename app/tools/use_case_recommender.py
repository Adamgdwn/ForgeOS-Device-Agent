from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class UseCaseRecommenderTool(BaseTool):
    name = "use_case_recommender"
    input_schema = {
        "device": "object",
        "assessment": "object",
        "user_profile": "object",
        "os_goals": "object",
        "connection_plan": "object",
    }
    output_schema = {"recommended_use_case": "string", "options": "array"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        device = dict(payload.get("device", {}))
        assessment = dict(payload.get("assessment", {}))
        user_profile = dict(payload.get("user_profile", {}))
        os_goals = dict(payload.get("os_goals", {}))
        connection_plan = dict(payload.get("connection_plan", {}))

        support_status = assessment.get("support_status", "research_only")
        technical_comfort = user_profile.get("technical_comfort", "low")
        priority = user_profile.get("primary_priority") or os_goals.get("top_goal", "security")
        transport_hint = device.get("transport", "unknown")
        adapter = connection_plan.get("recommended_adapter", {}).get("adapter_id", "unknown")

        options = [
            {
                "option_id": "accessibility_focused_phone",
                "label": "Accessibility-focused phone",
                "fit_score": 0.82 if priority in {"simplicity", "security"} else 0.55,
                "rationale": "A constrained, dependable phone profile suits users who need clarity, safer defaults, and fewer moving parts.",
                "constraints": ["Needs stable telephony and input support."],
                "evidence": [f"priority={priority}", f"technical_comfort={technical_comfort}"],
            },
            {
                "option_id": "media_device",
                "label": "Offline media device",
                "fit_score": 0.76 if support_status != "blocked" else 0.44,
                "rationale": "Media playback is often achievable even when deeper platform customization is still uncertain.",
                "constraints": ["Storage health and battery longevity matter."],
                "evidence": [f"support_status={support_status}", f"transport={transport_hint}"],
            },
            {
                "option_id": "home_control_panel",
                "label": "Home control panel",
                "fit_score": 0.72 if technical_comfort != "low" else 0.58,
                "rationale": "A docked, single-purpose control surface can extend the life of older devices with modest hardware requirements.",
                "constraints": ["Requires reliable charging placement and kiosk-style shell."],
                "evidence": [f"adapter={adapter}"],
            },
            {
                "option_id": "lightweight_custom_android",
                "label": "Lightweight custom Android",
                "fit_score": 0.67 if support_status == "actionable" else 0.35,
                "rationale": "A lightly customized Android path is the most maintainable route when transport, restore, and update paths are still developing.",
                "constraints": ["Needs a trustworthy build and preview path before install."],
                "evidence": [f"support_status={support_status}", f"adapter={adapter}"],
            },
        ]

        ranked = sorted(options, key=lambda option: option["fit_score"], reverse=True)
        recommended = ranked[0]["option_id"] if ranked else "research_hold"
        if support_status == "research_only" and transport_hint == "usb-mtp":
            recommended = "lightweight_custom_android"
        if support_status == "blocked":
            recommended = "media_device"

        return {
            "recommended_use_case": recommended,
            "options": ranked,
            "summary": f"ForgeOS recommends `{recommended}` as the best attainable use case with the current evidence.",
        }

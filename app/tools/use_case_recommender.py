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
        form_factor = str(device.get("form_factor", "unknown"))
        adapter = connection_plan.get("recommended_adapter", {}).get("adapter_id", "unknown")
        desired_end_product = str(user_profile.get("desired_end_product", "")).lower()
        intended_user = str(user_profile.get("intended_user", "")).lower()
        lawful_use_attested = bool(user_profile.get("lawful_use_attested", False))

        options = [
            {
                "option_id": "accessibility_focused_phone",
                "label": "Accessibility-focused phone",
                "fit_score": (0.82 if priority in {"simplicity", "security"} else 0.55)
                + self._keyword_bonus(desired_end_product, intended_user, ["senior", "accessibility", "simple", "phone"])
                + (0.05 if form_factor == "phone" else -0.08 if form_factor == "tablet" else 0.0),
                "rationale": "A constrained, dependable phone profile suits users who need clarity, safer defaults, and fewer moving parts.",
                "constraints": ["Needs stable telephony and input support."],
                "evidence": [f"priority={priority}", f"technical_comfort={technical_comfort}", f"form_factor={form_factor}"],
            },
            {
                "option_id": "media_device",
                "label": "Offline media device",
                "fit_score": (0.76 if support_status != "blocked" else 0.44)
                + self._keyword_bonus(desired_end_product, intended_user, ["media", "music", "video", "offline", "player"])
                + (0.08 if form_factor == "tablet" else 0.0),
                "rationale": "Media playback is often achievable even when deeper platform customization is still uncertain.",
                "constraints": ["Storage health and battery longevity matter."],
                "evidence": [f"support_status={support_status}", f"transport={transport_hint}", f"form_factor={form_factor}"],
            },
            {
                "option_id": "home_control_panel",
                "label": "Home control panel",
                "fit_score": (0.72 if technical_comfort != "low" else 0.58)
                + self._keyword_bonus(desired_end_product, intended_user, ["kiosk", "dashboard", "wall", "home", "control"])
                + (0.1 if form_factor == "tablet" else 0.0),
                "rationale": "A docked, single-purpose control surface can extend the life of older devices with modest hardware requirements.",
                "constraints": ["Requires reliable charging placement and kiosk-style shell."],
                "evidence": [f"adapter={adapter}", f"form_factor={form_factor}"],
            },
            {
                "option_id": "lightweight_custom_android",
                "label": "Lightweight custom Android",
                "fit_score": (0.67 if support_status == "actionable" else 0.35)
                + self._keyword_bonus(desired_end_product, intended_user, ["android", "custom", "tablet", "phone", "general"]),
                "rationale": "A lightly customized Android path is the most maintainable route when transport, restore, and update paths are still developing.",
                "constraints": ["Needs a trustworthy build and preview path before install."],
                "evidence": [f"support_status={support_status}", f"adapter={adapter}", f"form_factor={form_factor}"],
            },
        ]
        if not lawful_use_attested:
            options.append(
                {
                    "option_id": "research_hold",
                    "label": "Research and preview only",
                    "fit_score": 1.0,
                    "rationale": "ForgeOS can assess and plan, but install or bypass-style actions require an explicit authorization attestation.",
                    "constraints": ["No destructive execution or lock-bypass work without lawful authorization."],
                    "evidence": ["lawful_use_attested=false"],
                }
            )

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

    def _keyword_bonus(self, desired_end_product: str, intended_user: str, keywords: list[str]) -> float:
        haystack = f"{desired_end_product} {intended_user}"
        matches = sum(1 for keyword in keywords if keyword in haystack)
        return min(0.18, matches * 0.06)

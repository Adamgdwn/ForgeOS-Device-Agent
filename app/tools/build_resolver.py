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
        "recommendation": "object",
        "operator_review": "object",
    }
    output_schema = {"os_path": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        assessment = dict(payload.get("assessment", {}))
        connection_plan = dict(payload.get("connection_plan", {}))
        selected_strategy = str(payload.get("selected_strategy", "research_only"))
        user_profile = dict(payload.get("user_profile", {}))
        os_goals = dict(payload.get("os_goals", {}))
        recommendation = dict(payload.get("recommendation", {}))
        operator_review = dict(payload.get("operator_review", {}))

        if assessment.get("support_status") == "blocked":
            os_path = "blocked_path"
            reason = "The device is blocked by support or safety constraints."
        elif selected_strategy in {"transport_recovery", "research_only", "blocked_research"}:
            os_path = "research_only_path"
            reason = "A manageable transport and support baseline must exist before a build path can be chosen."
        elif selected_strategy == "hardened_stock":
            os_path = "hardened_stock_path"
            reason = "Profile and support evidence favor a stock-derived, maintainable path."
        elif selected_strategy in {"aftermarket_rom", "privacy_hardened_aftermarket"}:
            os_path = "aftermarket_path"
            reason = "The selected strategy favors an aftermarket or privacy-hardened path where support allows it."
        elif selected_strategy == "managed_family_build":
            os_path = "managed_family_path"
            reason = "The intended user profile favors a constrained, family-oriented build."
        elif selected_strategy == "device_specific_build":
            os_path = "device_specific_path"
            reason = "The selected strategy favors device-specific tuning and deeper customization."
        else:
            os_path = "maintainable_hardened_path"
            reason = "Default to the most maintainable hardened path while preserving room for later refinement."

        selected_option_id = self._selected_option_id(recommendation, operator_review, user_profile)
        option = self._selected_option(recommendation, selected_option_id)
        included_features, rejected_features = self._feature_decisions(option, operator_review, user_profile, os_goals)
        proposed_os_name = self._proposal_os_name(selected_option_id, os_path)
        artifact_requirements = self._artifact_requirements(os_path, included_features, rejected_features)
        summary = reason
        if selected_option_id:
            summary += f" ForgeOS is shaping this plan around `{selected_option_id}` with {len(included_features)} included feature decisions and {len(rejected_features)} rejected/default-off items."
        return {
            "os_path": os_path,
            "reason": summary,
            "selected_option_id": selected_option_id,
            "selected_option_label": option.get("label", self._labelize(selected_option_id)),
            "proposed_os_name": proposed_os_name,
            "included_feature_ids": [item["id"] for item in included_features],
            "included_feature_labels": [item["label"] for item in included_features],
            "rejected_feature_ids": [item["id"] for item in rejected_features],
            "rejected_feature_labels": [item["label"] for item in rejected_features],
            "artifact_requirements": artifact_requirements,
        }

    def _selected_option_id(
        self,
        recommendation: dict[str, object],
        operator_review: dict[str, object],
        user_profile: dict[str, object],
    ) -> str:
        return str(
            operator_review.get("selected_option_id")
            or recommendation.get("recommended_use_case")
            or user_profile.get("target_use_case")
            or "research_hold"
        )

    def _selected_option(self, recommendation: dict[str, object], selected_option_id: str) -> dict[str, object]:
        options = recommendation.get("options", []) or []
        for option in options:
            if option.get("option_id") == selected_option_id:
                return dict(option)
        return {"option_id": selected_option_id, "label": self._labelize(selected_option_id)}

    def _feature_decisions(
        self,
        option: dict[str, object],
        operator_review: dict[str, object],
        user_profile: dict[str, object],
        os_goals: dict[str, object],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        selected_option_id = str(option.get("option_id", "research_hold"))
        catalog = {item["id"]: item for item in self._default_feature_catalog(selected_option_id, user_profile, os_goals)}
        accepted_ids = list(operator_review.get("accepted_feature_ids", []) or [])
        rejected_ids = list(operator_review.get("rejected_feature_ids", []) or [])
        if accepted_ids:
            included = [catalog[feature_id] for feature_id in accepted_ids if feature_id in catalog]
        else:
            included = [item for item in catalog.values() if item.get("default", True)]
        rejected = [catalog[feature_id] for feature_id in rejected_ids if feature_id in catalog]
        for item in self._default_excluded_features(selected_option_id):
            if item["id"] not in {feature["id"] for feature in rejected}:
                rejected.append(item)
        return included, rejected

    def _default_feature_catalog(
        self,
        selected_option_id: str,
        user_profile: dict[str, object],
        os_goals: dict[str, object],
    ) -> list[dict[str, str | bool]]:
        google_pref = str(user_profile.get("google_services_preference", "keep_google"))
        base: dict[str, list[dict[str, str | bool]]] = {
            "accessibility_focused_phone": [
                {"id": "simple_launcher", "label": "Simplified launcher and larger touch targets", "default": True},
                {"id": "trusted_contacts", "label": "Trusted-contact shortcuts", "default": True},
                {"id": "accessibility_toggles", "label": "Accessibility quick toggles", "default": True},
                {"id": "operator_notes", "label": "Pinned operator notes in the setup flow", "default": True},
            ],
            "lightweight_custom_android": [
                {"id": "debloated_apps", "label": "Debloated app set", "default": True},
                {"id": "focused_home", "label": "Focused home screen", "default": True},
                {"id": "recovery_entry", "label": "Visible restore and recovery entry point", "default": True},
                {"id": "operator_notes", "label": "Pinned operator notes in the setup flow", "default": True},
            ],
            "media_device": [
                {"id": "offline_media", "label": "Offline media playback shell", "default": True},
                {"id": "large_controls", "label": "Large playback and volume controls", "default": True},
                {"id": "operator_notes", "label": "Pinned operator notes in the setup flow", "default": True},
            ],
            "home_control_panel": [
                {"id": "kiosk_mode", "label": "Single-purpose kiosk shell", "default": True},
                {"id": "control_tiles", "label": "Large control tiles", "default": True},
                {"id": "operator_notes", "label": "Pinned operator notes in the setup flow", "default": True},
            ],
        }
        features = list(base.get(selected_option_id, [
            {"id": "safe_defaults", "label": "Safe default configuration", "default": True},
            {"id": "restore_visibility", "label": "Visible restore and rollback path", "default": True},
        ]))
        if google_pref == "keep_google":
            features.append({"id": "google_services", "label": "Keep Google services compatibility", "default": True})
        elif google_pref == "reduce_google":
            features.append({"id": "reduced_google", "label": "Reduce Google services footprint", "default": True})
        else:
            features.append({"id": "minimize_google", "label": "Remove Google services where feasible", "default": True})
        if bool(os_goals.get("requires_reliable_updates", True)):
            features.append({"id": "update_channel", "label": "Preserve a reliable update path", "default": True})
        if bool(os_goals.get("prefers_lockdown_defaults", True)):
            features.append({"id": "lockdown_defaults", "label": "Hardened privacy and lockdown defaults", "default": True})
        if bool(os_goals.get("prefers_long_battery_life", True)):
            features.append({"id": "battery_profile", "label": "Battery-preserving runtime tuning", "default": True})
        return features

    def _default_excluded_features(self, selected_option_id: str) -> list[dict[str, str]]:
        excluded = [
            {"id": "wipe_autostart", "label": "Automatic wipe/install start"},
        ]
        if selected_option_id == "lightweight_custom_android":
            excluded.append({"id": "full_google_bundle", "label": "Full Google bundle"})
        return excluded

    def _artifact_requirements(
        self,
        os_path: str,
        included_features: list[dict[str, str]],
        rejected_features: list[dict[str, str]],
    ) -> list[str]:
        hints = [
            f"build-path:{os_path}",
            "proposal-manifest",
            "backup-bundle",
            "restore-plan",
        ]
        feature_ids = [item["id"] for item in included_features]
        hints.extend(f"feature:{feature_id}" for feature_id in feature_ids[:6])
        rejected_ids = [item["id"] for item in rejected_features]
        hints.extend(f"reject:{feature_id}" for feature_id in rejected_ids[:4])
        if os_path == "research_only_path":
            hints.append("concept-preview-only")
        return hints

    def _proposal_os_name(self, selected_option_id: str, os_path: str) -> str:
        option_name = self._labelize(selected_option_id)
        if os_path == "research_only_path":
            return f"{option_name} concept on a hardened stock Android baseline"
        if os_path in {"hardened_stock_path", "maintainable_hardened_path"}:
            return f"Hardened stock Android for {option_name}"
        if os_path == "aftermarket_path":
            return f"Aftermarket Android build for {option_name}"
        if os_path == "managed_family_path":
            return f"Managed family build for {option_name}"
        if os_path == "device_specific_path":
            return f"Device-specific tuned build for {option_name}"
        return f"{option_name} build on {os_path.replace('_', ' ')}"

    def _labelize(self, value: str) -> str:
        return value.replace("_", " ").replace("-", " ").strip().title()

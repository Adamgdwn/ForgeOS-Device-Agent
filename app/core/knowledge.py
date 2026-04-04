from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import DeviceProfile, SessionState, SupportStatus, utc_now


def _family_key(profile: DeviceProfile) -> str:
    manufacturer = (profile.manufacturer or "unknown").strip().lower().replace(" ", "-")
    model = (profile.model or "unknown").strip().lower().replace(" ", "-")
    return f"{manufacturer}:{model}"


class KnowledgeEngine:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.knowledge_dir = root / "knowledge"
        self.session_outcomes_path = self.knowledge_dir / "session_outcomes.json"
        self.support_matrix_path = self.knowledge_dir / "support_matrix.json"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def record_session_outcome(
        self,
        profile: DeviceProfile,
        state: SessionState,
        assessment: dict[str, Any],
    ) -> dict[str, Any]:
        outcomes = self._load_json(self.session_outcomes_path, {"outcomes": {}})
        family_key = _family_key(profile)
        outcomes["outcomes"][profile.session_id] = {
            "session_id": profile.session_id,
            "recorded_at": utc_now(),
            "family_key": family_key,
            "canonical_name": profile.canonical_name,
            "device_codename": profile.device_codename,
            "manufacturer": profile.manufacturer,
            "model": profile.model,
            "transport": profile.transport.value,
            "android_version": profile.android_version,
            "bootloader_locked": profile.bootloader_locked,
            "verified_boot_state": profile.verified_boot_state,
            "support_status": state.support_status.value,
            "selected_strategy": state.selected_strategy,
            "current_state": state.state.value,
            "restore_path_feasible": bool(assessment.get("restore_path_feasible")),
            "assessment_summary": assessment.get("summary"),
            "notes": state.notes[-5:],
        }
        self._write_json(self.session_outcomes_path, outcomes)
        matrix = self.rebuild_support_matrix()
        family = matrix["families"].get(family_key, {})
        return {
            "family_key": family_key,
            "support_level": family.get("support_level", "unknown"),
            "confidence": family.get("confidence", 0.0),
            "observations": family.get("observations", 0),
        }

    def rebuild_support_matrix(self) -> dict[str, Any]:
        outcomes = self._load_json(self.session_outcomes_path, {"outcomes": {}})
        families: dict[str, dict[str, Any]] = {}

        for outcome in outcomes["outcomes"].values():
            family_key = outcome["family_key"]
            family = families.setdefault(
                family_key,
                {
                    "manufacturer": outcome.get("manufacturer"),
                    "model": outcome.get("model"),
                    "observations": 0,
                    "actionable": 0,
                    "research_only": 0,
                    "blocked": 0,
                    "experimental": 0,
                    "restore_path_confirmed": 0,
                    "strategies": {},
                    "latest_summary": outcome.get("assessment_summary"),
                },
            )
            family["observations"] += 1
            family["latest_summary"] = outcome.get("assessment_summary")
            status = outcome.get("support_status", SupportStatus.RESEARCH_ONLY.value)
            family[status] = family.get(status, 0) + 1
            if outcome.get("restore_path_feasible"):
                family["restore_path_confirmed"] += 1
            strategy = outcome.get("selected_strategy") or "unselected"
            family["strategies"][strategy] = family["strategies"].get(strategy, 0) + 1

        for family in families.values():
            observations = max(1, family["observations"])
            actionable_rate = family["actionable"] / observations
            blocked_rate = family["blocked"] / observations
            restore_rate = family["restore_path_confirmed"] / observations
            confidence = min(
                0.98,
                0.15 + (0.12 * observations) + (0.35 * actionable_rate) + (0.2 * restore_rate) - (0.25 * blocked_rate),
            )
            confidence = round(max(0.05, confidence), 2)
            family["confidence"] = confidence
            family["recommended_strategy"] = max(
                family["strategies"].items(),
                key=lambda item: item[1],
            )[0] if family["strategies"] else "research_only"
            family["support_level"] = self._support_level_for_family(family, confidence)

        matrix = {
            "generated_at": utc_now(),
            "families": dict(sorted(families.items())),
        }
        self._write_json(self.support_matrix_path, matrix)
        return matrix

    def lookup_family_summary(self, manufacturer: str | None, model: str | None) -> dict[str, Any] | None:
        matrix = self._load_json(self.support_matrix_path, {"families": {}})
        family_key = f"{(manufacturer or 'unknown').strip().lower().replace(' ', '-')}:{(model or 'unknown').strip().lower().replace(' ', '-')}"
        family = matrix.get("families", {}).get(family_key)
        if not family:
            return None
        return {"family_key": family_key} | family

    def _support_level_for_family(self, family: dict[str, Any], confidence: float) -> str:
        observations = family["observations"]
        if family["blocked"] == observations and observations >= 1:
            return "blocked"
        if observations >= 3 and confidence >= 0.75 and family["actionable"] / observations >= 0.66:
            return "provisionally_supported"
        if observations >= 2 and confidence >= 0.55:
            return "developing"
        return "research_only"

    def _load_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        return json.loads(path.read_text())

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

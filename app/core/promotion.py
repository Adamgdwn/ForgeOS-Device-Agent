from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import utc_now


DEFAULT_RULES = {
    "min_observations_for_candidate": 3,
    "min_confidence_for_candidate": 0.75,
    "require_restore_path_ratio": 0.5,
    "require_non_research_strategy": True,
    "auto_apply_master_changes": False,
}


class PromotionEngine:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.promotion_dir = root / "promotion"
        self.rules_path = self.promotion_dir / "promotion_rules.json"
        self.candidates_path = self.promotion_dir / "candidates.json"
        self.promotion_dir.mkdir(parents=True, exist_ok=True)

    def evaluate(self, support_matrix: dict[str, Any]) -> dict[str, Any]:
        rules = self._load_json(self.rules_path, DEFAULT_RULES)
        candidates: list[dict[str, Any]] = []

        for family_key, family in support_matrix.get("families", {}).items():
            observations = family.get("observations", 0)
            confidence = family.get("confidence", 0.0)
            restore_ratio = family.get("restore_path_confirmed", 0) / max(1, observations)
            recommended_strategy = family.get("recommended_strategy", "research_only")

            meets = (
                observations >= rules["min_observations_for_candidate"]
                and confidence >= rules["min_confidence_for_candidate"]
                and restore_ratio >= rules["require_restore_path_ratio"]
            )
            if rules["require_non_research_strategy"] and recommended_strategy == "research_only":
                meets = False
            if not meets:
                continue

            candidates.append(
                {
                    "family_key": family_key,
                    "manufacturer": family.get("manufacturer"),
                    "model": family.get("model"),
                    "confidence": confidence,
                    "observations": observations,
                    "recommended_strategy": recommended_strategy,
                    "support_level": family.get("support_level"),
                    "promotion_status": "review_required",
                    "auto_apply_allowed": bool(rules.get("auto_apply_master_changes")),
                    "proposed_updates": [
                        "master/strategies/default_strategies.json",
                        "master/manifests/sources.json",
                        "master/testplans/default_validation_plan.json",
                    ],
                    "reason": (
                        "Repeated session evidence suggests this device family is stable enough "
                        "for human-reviewed promotion into the master framework."
                    ),
                }
            )

        payload = {
            "generated_at": utc_now(),
            "rules": rules,
            "candidates": candidates,
        }
        self._write_json(self.candidates_path, payload)
        return payload

    def _load_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            self._write_json(path, default)
            return default
        return json.loads(path.read_text())

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

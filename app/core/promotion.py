from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from app.core.models import utc_now

if TYPE_CHECKING:
    from app.core.adapter_registry import AdapterRegistry


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

    def apply_to_master(
        self,
        adapter_registry: "AdapterRegistry",
        candidate_key: str,
    ) -> dict[str, Any]:
        """Copy a promotion-ready adapter from promotion/adapters/<key>/ into master/.

        Writes:
          master/integrations/oem_adapters/<key>.py
          master/playbooks/connection/<key>.json

        Safe to call multiple times — overwrites existing master files.
        """
        review_dir = adapter_registry.get_review_dir_by_key(candidate_key)
        meta_path = review_dir / "meta.json"
        if not meta_path.exists():
            return {
                "status": "skipped",
                "reason": f"No promotion candidate found at {review_dir}",
                "candidate_key": candidate_key,
            }
        meta = json.loads(meta_path.read_text())
        src_adapter = Path(str(meta["adapter_path"]))
        src_playbook = Path(str(meta["playbook_path"]))
        if not src_adapter.exists():
            return {
                "status": "skipped",
                "reason": f"Adapter source file missing: {src_adapter}",
                "candidate_key": candidate_key,
            }

        dest_adapter = adapter_registry.get_master_adapter_path_by_key(candidate_key)
        dest_playbook = adapter_registry.get_master_playbook_path_by_key(candidate_key)
        dest_adapter.parent.mkdir(parents=True, exist_ok=True)
        dest_playbook.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src_adapter, dest_adapter)
        if src_playbook.exists():
            shutil.copy2(src_playbook, dest_playbook)

        # Update meta to reflect promotion
        meta["status"] = "promoted"
        meta["master_adapter_path"] = str(dest_adapter)
        meta["master_playbook_path"] = str(dest_playbook)
        meta["promoted_at"] = utc_now()
        meta_path.write_text(json.dumps(meta, indent=2))

        return {
            "status": "promoted",
            "candidate_key": candidate_key,
            "master_adapter_path": str(dest_adapter),
            "master_playbook_path": str(dest_playbook),
            "summary": (
                f"Adapter `{candidate_key}` promoted to master — "
                f"future sessions for {meta.get('manufacturer')} {meta.get('model')} "
                "will load this adapter automatically."
            ),
        }

    def deprecate_adapter(self, family_key: str, reason: str) -> None:
        adapter_src = self.root / "master" / "integrations" / "oem_adapters" / f"{family_key}.py"
        playbook_src = self.root / "master" / "playbooks" / "connection" / f"{family_key}.json"
        deprecated_dir = self.root / "master" / "integrations" / "oem_adapters" / "_deprecated" / (
            f"{family_key}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        deprecated_dir.mkdir(parents=True, exist_ok=True)
        if adapter_src.exists():
            shutil.move(str(adapter_src), str(deprecated_dir / adapter_src.name))
        if playbook_src.exists():
            shutil.move(str(playbook_src), str(deprecated_dir / playbook_src.name))
        (deprecated_dir / "deprecation.json").write_text(
            json.dumps(
                {
                    "deprecated_at": utc_now(),
                    "reason": reason,
                    "family_key": family_key,
                },
                indent=2,
            )
        )

        if self.root.joinpath("knowledge", "support_matrix.json").exists():
            matrix = self._load_json(self.root / "knowledge" / "support_matrix.json", {"families": {}})
            if family_key in matrix.get("families", {}):
                matrix["families"][family_key]["support_level"] = "deprecated"
                matrix["families"][family_key]["deprecated_reason"] = reason
            self._write_json(self.root / "knowledge" / "support_matrix.json", matrix)

    def audit_promoted_adapters(self) -> list[str]:
        flagged: list[str] = []
        outcomes = self._load_json(self.root / "knowledge" / "session_outcomes.json", {"outcomes": {}})
        confirmed_families = {
            f"{str(outcome.get('manufacturer') or '').strip().lower().replace(' ', '_')}_{str(outcome.get('model') or '').strip().lower().replace(' ', '_')}"
            for outcome in outcomes.get("outcomes", {}).values()
            if str(outcome.get("serial") or "") and not str(outcome.get("serial") or "").startswith("usb-")
        }
        if not (self.root / "promotion" / "adapters").exists():
            return flagged
        for meta_path in sorted((self.root / "promotion" / "adapters").glob("*/meta.json")):
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                continue
            key = str(meta.get("key") or meta_path.parent.name)
            if str(meta.get("status", "")) != "promoted":
                continue
            test_source = str(meta.get("test_source") or meta.get("test_result", {}).get("status", ""))
            if test_source != "probe_no_device":
                continue
            if key not in confirmed_families:
                flagged.append(key)
        return flagged

    def _load_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            self._write_json(path, default)
            return default
        return json.loads(path.read_text())

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))

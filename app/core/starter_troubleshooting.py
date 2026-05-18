from __future__ import annotations

from pathlib import Path
from typing import Any

import json

from app.core.io_utils import atomic_write_json
from app.core.models import DeviceProfile, utc_now


class StarterTroubleshootingLoop:
    """Deterministic first-pass troubleshooting before model workers are allowed."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.memory_path = root / "knowledge" / "starter_troubleshooting_memory.json"

    def run(
        self,
        *,
        session_dir: Path,
        profile: DeviceProfile,
        build_plan: dict[str, Any],
        build_artifacts: dict[str, Any],
        blocker: dict[str, Any],
        deliberation: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = self._hardware_snapshot(profile)
        artifact_review = self._review_staged_artifacts(session_dir, snapshot)
        product_memory = dict(build_plan.get("product_memory") or {})
        version_memory = dict(product_memory.get("version") or {})
        learned_rules = self._compile_learned_rules(product_memory)
        source_acquisition = dict(build_plan.get("source_acquisition") or {})
        builder = dict(source_acquisition.get("builder") or {})
        execution_policy = dict((deliberation.get("action_plan") or {}).get("execution_policy") or {})

        blocker_type = str(blocker.get("blocker_type") or "none")
        repeated_source_blocker = int((version_memory.get("blockers") or {}).get("source_blocker", 0)) >= 3
        repo_missing = "repo tool is missing" in str(builder.get("reason") or "").lower()
        learned_repo_prereq = any(rule["rule_id"] == "require_android_repo_before_source_build" for rule in learned_rules)
        has_compatible_artifact = bool(artifact_review["accepted_artifacts"])
        has_rejected_artifact = bool(artifact_review["rejected_artifacts"])
        deliberation_allows_machine = bool(execution_policy.get("machine_remediation_allowed", True))

        status = "ready_for_bounded_model_help"
        model_worker_allowed = True
        machine_worker_allowed = deliberation_allows_machine
        next_actions: list[str] = []
        notes: list[str] = []

        if blocker_type == "source_blocker" and has_rejected_artifact and not has_compatible_artifact:
            status = "blocked_incompatible_artifact"
            model_worker_allowed = False
            machine_worker_allowed = False
            next_actions.extend(
                [
                    "Replace the incompatible staged artifact with an exact Samsung SM-T377W/gteslte OTA, recovery ZIP, or Samsung firmware package.",
                    "Do not flash generic arm64 A/B system images to this non-Treble 32-bit tablet.",
                ]
            )
        elif blocker_type == "source_blocker" and (repo_missing or learned_repo_prereq or repeated_source_blocker) and not has_compatible_artifact:
            status = "waiting_for_source_or_host_setup"
            model_worker_allowed = False
            machine_worker_allowed = False
            next_actions.extend(
                [
                    "Stage a verified firmware/OTA/recovery package for Samsung SM-T377W/gteslte.",
                    "Or approve host setup for Android source builds, including the Android repo tool.",
                ]
            )
        elif not deliberation_allows_machine:
            status = "waiting_for_operator_answer"
            model_worker_allowed = False
            machine_worker_allowed = False
            next_actions.extend((deliberation.get("action_plan") or {}).get("operator_questions") or [])

        if build_artifacts.get("status") != "ready":
            notes.append("No deterministic install path is ready yet.")
        if repo_missing:
            notes.append("Local Android source builds are blocked until the Android repo tool is available.")
        if learned_repo_prereq:
            notes.append("Product memory already learned that source builds need Android repo setup first.")
        if repeated_source_blocker:
            notes.append("This product/version has repeatedly hit source acquisition blockers.")
        if has_rejected_artifact:
            notes.append("One or more staged artifacts were rejected before model escalation.")

        result = {
            "generated_at": utc_now(),
            "status": status,
            "blocker_type": blocker_type,
            "model_worker_allowed": model_worker_allowed,
            "machine_worker_allowed": machine_worker_allowed,
            "next_actions": self._dedupe(next_actions),
            "notes": self._dedupe(notes),
            "artifact_review": artifact_review,
            "host_prerequisites": {
                "android_repo_missing": repo_missing,
                "builder_status": builder.get("status"),
                "builder_reason": builder.get("reason"),
            },
            "memory_checks": {
                "product_key": product_memory.get("product_key"),
                "version_key": product_memory.get("version_key"),
                "source_blocker_count": int((version_memory.get("blockers") or {}).get("source_blocker", 0)),
                "lessons": version_memory.get("lessons", []),
            },
            "learned_augmentations": learned_rules,
        }
        atomic_write_json(session_dir / "runtime" / "troubleshooting" / "starter-loop.json", result)
        self._record_memory_overlay(result)
        return result

    def _compile_learned_rules(self, product_memory: dict[str, Any]) -> list[dict[str, Any]]:
        version = dict(product_memory.get("version") or {})
        lessons = [str(lesson) for lesson in version.get("lessons", [])]
        rules: list[dict[str, Any]] = []
        joined = " ".join(lessons).lower()
        if "repo tool" in joined:
            rules.append(
                {
                    "rule_id": "require_android_repo_before_source_build",
                    "source": "product_version_memory",
                    "behavior": "Do not start another local Android source-build worker until Android repo setup changes.",
                }
            )
        if "no usable flashable artifact" in joined:
            rules.append(
                {
                    "rule_id": "require_verified_flashable_artifact",
                    "source": "product_version_memory",
                    "behavior": "Keep install planning blocked until an exact OTA, recovery ZIP, Samsung firmware archive, or partition bundle is verified.",
                }
            )
        if "repeatedly reaches source acquisition" in joined:
            rules.append(
                {
                    "rule_id": "prefer_artifact_or_host_setup_over_more_research",
                    "source": "product_version_memory",
                    "behavior": "Use product-specific artifact staging or host setup questions before asking broad model research prompts again.",
                }
            )
        return rules

    def _record_memory_overlay(self, result: dict[str, Any]) -> None:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._load_memory_overlay()
        key = str(result.get("memory_checks", {}).get("product_key") or "unknown")
        version_key = str(result.get("memory_checks", {}).get("version_key") or "unknown")
        products = payload.setdefault("products", {})
        product = products.setdefault(key, {"versions": {}})
        product["last_seen"] = result["generated_at"]
        product["versions"][version_key] = {
            "last_seen": result["generated_at"],
            "last_status": result.get("status"),
            "learned_augmentations": result.get("learned_augmentations", []),
            "last_next_actions": result.get("next_actions", []),
        }
        payload["generated_at"] = result["generated_at"]
        atomic_write_json(self.memory_path, payload)

    def _load_memory_overlay(self) -> dict[str, Any]:
        if not self.memory_path.exists():
            return {"generated_at": utc_now(), "products": {}}
        try:
            loaded = json.loads(self.memory_path.read_text())
        except json.JSONDecodeError:
            return {"generated_at": utc_now(), "products": {}}
        return loaded if isinstance(loaded, dict) else {"generated_at": utc_now(), "products": {}}

    def _review_staged_artifacts(self, session_dir: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
        source_dir = session_dir / "artifacts" / "os-source"
        abi = str(snapshot.get("abi") or "").lower()
        boot_slot = str(snapshot.get("boot_slot") or "").strip()
        dynamic_partitions = str(snapshot.get("dynamic_partitions") or "").strip().lower() in {"1", "true", "yes"}

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        if not source_dir.exists():
            return {"source_dir": str(source_dir), "accepted_artifacts": accepted, "rejected_artifacts": rejected}

        for path in sorted(source_dir.iterdir()):
            if not path.is_file() or path.name == "README.md":
                continue
            reason = self._artifact_rejection_reason(path, abi=abi, boot_slot=boot_slot, dynamic_partitions=dynamic_partitions)
            item = {"path": str(path), "name": path.name, "size_bytes": path.stat().st_size}
            if reason:
                rejected.append({**item, "reason": reason})
            else:
                accepted.append(item)
        return {"source_dir": str(source_dir), "accepted_artifacts": accepted, "rejected_artifacts": rejected}

    def _artifact_rejection_reason(self, path: Path, *, abi: str, boot_slot: str, dynamic_partitions: bool) -> str:
        name = path.name.lower()
        if "arm64" in name and abi == "armeabi-v7a":
            return "artifact targets arm64 but device reports 32-bit armeabi-v7a"
        if ("-ab" in name or "_ab" in name or "a-b" in name) and not boot_slot and not dynamic_partitions:
            return "artifact appears to target A/B or dynamic-partition devices, but this device exposes no slot/dynamic-partition evidence"
        if name.endswith(".img.xz"):
            return "compressed raw image is not directly flashable; extract and verify compatibility first"
        return ""

    def _hardware_snapshot(self, profile: DeviceProfile) -> dict[str, Any]:
        raw = dict(profile.raw_probe_data or {})
        return dict(raw.get("hardware_snapshot") or {})

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        output = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output

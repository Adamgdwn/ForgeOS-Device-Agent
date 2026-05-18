from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import utc_now


class DeliberationEngine:
    """Executive control loop for turning observations into a constrained next action."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def think(
        self,
        *,
        session_dir: Path,
        profile: Any,
        state: Any,
        assessment: dict[str, Any],
        engagement: dict[str, Any],
        connection_plan: dict[str, Any],
        build_plan: dict[str, Any],
        build_artifacts: dict[str, Any],
        blocker: dict[str, Any],
        recommendation: dict[str, Any],
        user_profile: Any,
        product_memory: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        thinking_dir = session_dir / "runtime" / "thinking"
        thinking_dir.mkdir(parents=True, exist_ok=True)
        previous = self._read_json(thinking_dir / "current-situation.json")
        lessons = self._derive_lessons(session_dir=session_dir, blocker=blocker, build_artifacts=build_artifacts)
        situation = self._situation(
            session_dir=session_dir,
            profile=profile,
            state=state,
            assessment=assessment,
            engagement=engagement,
            connection_plan=connection_plan,
            build_plan=build_plan,
            build_artifacts=build_artifacts,
            blocker=blocker,
            recommendation=recommendation,
            user_profile=user_profile,
            product_memory=product_memory or {},
            lessons=lessons,
            previous=previous,
        )
        action_plan = self._action_plan(situation=situation, lessons=lessons, user_profile=user_profile)
        journal_entry = self._journal_entry(situation=situation, action_plan=action_plan)

        current_path = thinking_dir / "current-situation.json"
        action_path = thinking_dir / "action-plan.json"
        lessons_path = thinking_dir / "lessons-learned.json"
        journal_path = thinking_dir / "decision-journal.jsonl"
        self._write_json(current_path, situation)
        self._write_json(action_path, action_plan)
        self._write_json(lessons_path, {"generated_at": utc_now(), "lessons": lessons})
        with journal_path.open("a") as handle:
            handle.write(json.dumps(journal_entry) + "\n")

        return {
            "situation": situation,
            "action_plan": action_plan,
            "lessons": lessons,
            "journal_entry": journal_entry,
            "files": {
                "current_situation_path": str(current_path),
                "action_plan_path": str(action_path),
                "lessons_path": str(lessons_path),
                "decision_journal_path": str(journal_path),
            },
        }

    def _situation(
        self,
        *,
        session_dir: Path,
        profile: Any,
        state: Any,
        assessment: dict[str, Any],
        engagement: dict[str, Any],
        connection_plan: dict[str, Any],
        build_plan: dict[str, Any],
        build_artifacts: dict[str, Any],
        blocker: dict[str, Any],
        recommendation: dict[str, Any],
        user_profile: Any,
        product_memory: dict[str, Any],
        lessons: list[dict[str, Any]],
        previous: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_manifest = self._read_json(session_dir / "runtime" / "build" / "artifact-manifest.json")
        source_transcript = self._read_json(session_dir / "runtime" / "build-from-source" / "build-transcript.json")
        retry_heat = self._read_json(session_dir / "reports" / "retry-heat.json")
        experiments = self._read_json(session_dir / "reports" / "autonomous-experiments.json")
        blocker_type = str(blocker.get("blocker_type", "none"))
        repeated_blocker_count = self._repeated_blocker_count(retry_heat, blocker_type)
        source_dir = Path(str(artifact_manifest.get("source_dir") or session_dir / "artifacts" / "os-source"))
        plausible_source_files = self._plausible_source_files(source_dir)
        facts = {
            "device": {
                "manufacturer": getattr(profile, "manufacturer", ""),
                "model": getattr(profile, "model", ""),
                "codename": getattr(profile, "device_codename", ""),
                "serial": getattr(profile, "serial", ""),
                "form_factor": getattr(getattr(profile, "form_factor", ""), "value", getattr(profile, "form_factor", "")),
                "transport": getattr(getattr(profile, "transport", ""), "value", getattr(profile, "transport", "")),
            },
            "session": {
                "state": getattr(getattr(state, "state", ""), "value", getattr(state, "state", "")),
                "selected_strategy": getattr(state, "selected_strategy", ""),
                "remediation_iteration": getattr(state, "remediation_iteration", 0),
            },
            "support_status": assessment.get("support_status"),
            "engagement_status": engagement.get("engagement_status"),
            "recommended_use_case": recommendation.get("recommended_use_case"),
            "recommended_path": build_plan.get("os_path"),
            "artifact_status": build_artifacts.get("status"),
            "plausible_source_files": plausible_source_files,
            "source_build_status": source_transcript.get("status"),
            "source_build_error": source_transcript.get("stderr", ""),
            "blocker_type": blocker_type,
            "blocker_machine_solvable": bool(blocker.get("machine_solvable")),
            "repeated_blocker_count": repeated_blocker_count,
            "failed_experiment_count": self._failed_experiment_count(experiments, blocker_type),
            "product_memory": {
                "product_key": product_memory.get("product_key"),
                "version_key": product_memory.get("version_key"),
                "observations": (product_memory.get("product") or {}).get("observations")
                or product_memory.get("observations", 0),
                "reusable_guidance": (product_memory.get("product") or {}).get("reusable_guidance")
                or product_memory.get("reusable_guidance", []),
                "version_lessons": (product_memory.get("version") or {}).get("lessons", []),
            },
        }
        unknowns = []
        if not facts["device"]["model"] or str(facts["device"]["model"]).lower() == "unknown":
            unknowns.append("Exact model identity is not stable enough.")
        if not plausible_source_files and blocker_type == "source_blocker":
            unknowns.append("No real firmware, OTA, or image artifact has been staged.")
        if "repo tool is required" in str(facts["source_build_error"]).lower():
            unknowns.append("Android repo tool is missing, so local Android source builds cannot run.")
        version_lessons = list(facts.get("product_memory", {}).get("version_lessons") or [])
        if version_lessons:
            unknowns.extend(f"Product memory: {lesson}" for lesson in version_lessons[:3])
        if not getattr(user_profile, "desired_end_product", "").strip():
            unknowns.append("The operator has not fully described the desired end product.")
        changes = self._changes(previous.get("facts", {}), facts)
        return {
            "generated_at": utc_now(),
            "mission": "Save the connected device from the waste stream by producing a safe, useful, restorable configuration.",
            "facts": facts,
            "unknowns": unknowns,
            "active_blocker": blocker,
            "lessons_considered": lessons,
            "changes_since_last_cycle": changes,
        }

    def _action_plan(self, *, situation: dict[str, Any], lessons: list[dict[str, Any]], user_profile: Any) -> dict[str, Any]:
        facts = dict(situation.get("facts", {}))
        lesson_ids = {lesson["id"] for lesson in lessons}
        blocker_type = str(facts.get("blocker_type", "none"))
        machine_solvable = bool(facts.get("blocker_machine_solvable"))
        options = [
            self._option(
                "continue_remediation",
                "Run bounded machine remediation against the current blocker.",
                likely="Useful only when the blocker has not already failed the same way.",
                failure="Can waste time or duplicate generated artifacts if no new evidence exists.",
                second_order="Repeated bad retries pollute memory and make the agent look busy instead of useful.",
            ),
            self._option(
                "ask_operator",
                "Ask one targeted question or request one missing resource.",
                likely="Clarifies the desired outcome or obtains a real firmware/source input.",
                failure="Pauses autonomy if the question is too broad.",
                second_order="A precise question prevents destructive or irrelevant work.",
            ),
            self._option(
                "install_host_tool_or_stage_source",
                "Stop generated remediation and address the missing host/source prerequisite.",
                likely="Unblocks real source/build work when the operator installs `repo` or stages firmware.",
                failure="Requires operator action outside A1 autonomy.",
                second_order="Prevents the agent from fabricating artifacts or hammering unsupported web paths.",
            ),
        ]
        machine_remediation_allowed = machine_solvable
        selected_action = "continue_remediation" if machine_solvable else "observe_or_ask"
        rationale = "The blocker is machine-solvable and no learning rule blocks another bounded attempt."
        questions: list[str] = []

        if not getattr(user_profile, "desired_end_product", "").strip():
            questions.append("What should this device become when it is done: media player, family tablet, control panel, backup phone, or something else?")
        if blocker_type == "source_blocker" and not facts.get("plausible_source_files"):
            questions.append("Can you stage a real firmware/OTA/image package for this exact device, or should ForgeOS prepare the host to build/source one?")
        if "missing_android_repo_tool" in lesson_ids:
            machine_remediation_allowed = False
            selected_action = "install_host_tool_or_stage_source"
            rationale = "Local Android source build already failed because the `repo` tool is missing."
            questions.append("May I install/configure the Android `repo` tool for local source builds, or should we stay on firmware-staging only?")
        elif "repeated_non_advancing_source_attempts" in lesson_ids:
            machine_remediation_allowed = False
            selected_action = "ask_operator"
            rationale = "Repeated source acquisition attempts did not advance; the next useful step needs new evidence or a real artifact."
        elif facts.get("product_memory", {}).get("version_lessons"):
            rationale = "Prior product/version memory is available and should constrain the next remediation attempt."

        return {
            "generated_at": utc_now(),
            "primary_goal": "Produce a safe, useful, restorable device configuration from old hardware.",
            "goal_stack": [
                "Confirm the operator's desired end product.",
                "Preserve backup and restore confidence.",
                "Establish a real artifact or source path.",
                "Preview and verify before any destructive install.",
                "Avoid repeated non-advancing work.",
            ],
            "selected_action": selected_action,
            "rationale": rationale,
            "operator_questions": self._dedupe(questions)[:3],
            "options_considered": options,
            "execution_policy": {
                "machine_remediation_allowed": machine_remediation_allowed,
                "worker_mode": "bounded_remediation" if machine_remediation_allowed else "research_and_operator_question",
                "never_stage_mock_artifacts": True,
                "requires_new_evidence_for_repeat": True,
            },
        }

    def _journal_entry(self, *, situation: dict[str, Any], action_plan: dict[str, Any]) -> dict[str, Any]:
        facts = dict(situation.get("facts", {}))
        return {
            "timestamp": utc_now(),
            "blocker_type": facts.get("blocker_type"),
            "selected_action": action_plan.get("selected_action"),
            "rationale": action_plan.get("rationale"),
            "expected_evidence": [
                "new plausible firmware/source artifact",
                "clear host prerequisite status",
                "operator answer to the highest-value question",
            ],
            "stop_conditions": [
                "same blocker repeats without new evidence",
                "generated artifact emits mock/placeholders",
                "destructive gate remains unmet",
            ],
        }

    def _derive_lessons(
        self,
        *,
        session_dir: Path,
        blocker: dict[str, Any],
        build_artifacts: dict[str, Any],
    ) -> list[dict[str, Any]]:
        lessons: list[dict[str, Any]] = []
        source_transcript = self._read_json(session_dir / "runtime" / "build-from-source" / "build-transcript.json")
        if "repo tool is required" in str(source_transcript.get("stderr", "")).lower():
            lessons.append(
                {
                    "id": "missing_android_repo_tool",
                    "summary": "Local Android source builds cannot run until the host has the Android repo tool.",
                    "behavior_change": "Do not keep launching source-build remediation; ask for host setup or a staged artifact.",
                }
            )
        experiments = self._read_json(session_dir / "reports" / "autonomous-experiments.json")
        failed_same = self._failed_experiment_count(experiments, str(blocker.get("blocker_type", "none")))
        if failed_same >= 2:
            lessons.append(
                {
                    "id": "repeated_non_advancing_source_attempts",
                    "summary": "Multiple experiments on this blocker were discarded without advancing the session.",
                    "behavior_change": "Require new evidence before another machine-remediation loop.",
                }
            )
        details = dict(build_artifacts.get("details") or {})
        if details.get("missing_requirements") and str(blocker.get("blocker_type")) == "source_blocker":
            lessons.append(
                {
                    "id": "real_artifact_required",
                    "summary": "A real OTA, firmware archive, or partition image is required; mock files are not progress.",
                    "behavior_change": "Reject placeholder artifacts and keep install gates closed.",
                }
            )
        return lessons

    def _option(self, option_id: str, action: str, *, likely: str, failure: str, second_order: str) -> dict[str, str]:
        return {
            "option_id": option_id,
            "action": action,
            "likely_outcome": likely,
            "failure_mode": failure,
            "second_order_consequence": second_order,
        }

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text())
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2))
        tmp_path.replace(path)

    def _changes(self, previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
        changes = []
        for key, value in current.items():
            if previous.get(key) != value:
                changes.append({"field": key, "from": previous.get(key), "to": value})
        return changes[:12]

    def _repeated_blocker_count(self, retry_heat: dict[str, Any], blocker_type: str) -> int:
        count = 0
        for cycle in reversed(list(retry_heat.get("cycles") or [])):
            if cycle.get("blocker_type") != blocker_type or cycle.get("advanced") is True:
                break
            count += 1
        return count

    def _failed_experiment_count(self, experiments: dict[str, Any], blocker_type: str) -> int:
        count = 0
        for experiment in reversed(list(experiments.get("experiments") or [])):
            if experiment.get("blocker_before") != blocker_type:
                continue
            if experiment.get("advanced") is True:
                break
            count += 1
        return count

    def _plausible_source_files(self, source_dir: Path) -> list[str]:
        if not source_dir.exists():
            return []
        files = []
        for path in sorted(source_dir.iterdir()):
            if not path.is_file() or path.name == "README.md":
                continue
            if path.suffix.lower() not in {".zip", ".img", ".gz", ".tar", ".bin"}:
                continue
            try:
                if path.stat().st_size < 1024 * 1024:
                    continue
                sample = path.read_bytes()[:256].lower()
            except OSError:
                continue
            if any(marker in sample for marker in [b"mock content", b"simulated firmware content", b"placeholder"]):
                continue
            files.append(str(path))
        return files

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        output = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output

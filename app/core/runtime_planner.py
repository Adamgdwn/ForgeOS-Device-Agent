from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from app.core.models import (
    ApprovalGate,
    RecommendationOption,
    RuntimePhase,
    RuntimeSessionPlan,
    SessionState,
    SessionStateName,
    VerificationExecution,
    PreviewExecution,
    WorkerExecution,
    WorkerRouteDecision,
    to_dict,
)
from app.core.session_manager import SessionManager


STATE_TO_PHASE: dict[SessionStateName, RuntimePhase] = {
    SessionStateName.INTAKE: RuntimePhase.INTAKE,
    SessionStateName.ACCESS_ENABLEMENT: RuntimePhase.ACCESS,
    SessionStateName.DEEP_SCAN: RuntimePhase.DISCOVERY,
    SessionStateName.DISCOVER: RuntimePhase.DISCOVERY,
    SessionStateName.ASSESS: RuntimePhase.DISCOVERY,
    SessionStateName.RECOMMEND: RuntimePhase.RECOMMENDATION,
    SessionStateName.BACKUP_PLAN: RuntimePhase.BACKUP,
    SessionStateName.BACKUP_READY: RuntimePhase.BACKUP,
    SessionStateName.PREVIEW_BUILD: RuntimePhase.PREVIEW,
    SessionStateName.PREVIEW_REVIEW: RuntimePhase.PREVIEW,
    SessionStateName.INTERACTIVE_VERIFY: RuntimePhase.VERIFICATION,
    SessionStateName.INSTALL_APPROVAL: RuntimePhase.INSTALL,
    SessionStateName.FLASH_PREP: RuntimePhase.INSTALL,
    SessionStateName.FLASH: RuntimePhase.INSTALL,
    SessionStateName.POST_INSTALL_VERIFY: RuntimePhase.POST_INSTALL,
    SessionStateName.COMPLETE: RuntimePhase.COMPLETE,
    SessionStateName.BLOCKED: RuntimePhase.BLOCKED,
}


class RuntimePlanner:
    def __init__(self, root: Path, sessions: SessionManager) -> None:
        self.root = root
        self.sessions = sessions

    def materialize(
        self,
        session_dir: Path,
        state: SessionState,
        assessment: dict[str, Any],
        connection_plan: dict[str, Any],
        build_plan: dict[str, Any],
        backup_plan: dict[str, Any],
        restore_plan: dict[str, Any],
        blocker: dict[str, Any],
        worker_routes: list[WorkerRouteDecision],
        worker_executions: list[WorkerExecution],
        install_gate: ApprovalGate,
        runtime_gate: ApprovalGate,
        recommendation: dict[str, Any],
        preview_execution: PreviewExecution,
        verification_execution: VerificationExecution,
        governance_summary: dict[str, Any] | None = None,
        self_improvement_summary: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        plan = RuntimeSessionPlan(
            session_id=state.session_id,
            phase=self._phase_for_state(
                state,
                assessment=assessment,
                build_plan=build_plan,
                backup_plan=backup_plan,
                install_gate=install_gate,
                preview_execution=preview_execution,
                verification_execution=verification_execution,
            ),
            mission="Rehabilitate this device into a safe, useful, restorable system with the least-risk path available.",
            operator_summary=self._operator_summary(assessment, build_plan, blocker, install_gate),
            recommended_use_case=recommendation.get("recommended_use_case", "research_hold"),
            recommended_path=build_plan.get("os_path", "research_only_path"),
            worker_routes=worker_routes,
            worker_executions=worker_executions,
            recommendation_options=self._options_from_recommendation(recommendation),
            approval_gates=[runtime_gate, install_gate],
            preview_execution=preview_execution,
            verification_execution=verification_execution,
            evidence=self._evidence_paths(session_dir),
            next_actions=self._next_actions(blocker, install_gate),
            hard_stops=self._hard_stops(blocker, install_gate),
        )

        files = {
            "runtime_plan_path": str(
                self.sessions.write_runtime_artifact(session_dir, "runtime/session-plan.json", to_dict(plan))
            ),
            "proposal_manifest_path": str(
                self.sessions.write_runtime_artifact(
                    session_dir,
                    "runtime/proposal/proposal-manifest.json",
                    self._proposal_manifest(
                        session_dir=session_dir,
                        build_plan=build_plan,
                        recommendation=recommendation,
                        preview_execution=preview_execution,
                    ),
                )
            ),
            "worker_routing_path": str(
                self.sessions.write_runtime_artifact(
                    session_dir,
                    "runtime/worker-routing.json",
                    {
                        "session_id": state.session_id,
                        "routes": [to_dict(route) for route in worker_routes],
                        "executions": [to_dict(execution) for execution in worker_executions],
                    },
                )
            ),
            "audit_log_path": str(
                self.sessions.write_runtime_artifact(
                    session_dir,
                    "runtime/runtime-audit.json",
                    {
                        "session_id": state.session_id,
                        "phase": plan.phase.value,
                        "recommended_use_case": plan.recommended_use_case,
                        "recommended_path": plan.recommended_path,
                        "hard_stops": plan.hard_stops,
                        "next_actions": plan.next_actions,
                        "governance_summary": governance_summary or {},
                        "self_improvement_summary": self_improvement_summary or {},
                    },
                )
            ),
            "experiment_log_path": str(session_dir / "reports" / "autonomous-experiments.json"),
        }
        return files

    def _proposal_manifest(
        self,
        *,
        session_dir: Path,
        build_plan: dict[str, Any],
        recommendation: dict[str, Any],
        preview_execution: PreviewExecution,
    ) -> dict[str, Any]:
        user_profile = self.sessions.load_user_profile(session_dir)
        os_goals = self.sessions.load_os_goals(session_dir)
        operator_review = self._read_operator_review(session_dir)
        recommended_use_case = recommendation.get("recommended_use_case", "research_hold")
        recommended_path = build_plan.get("os_path", "research_only_path")
        selected_option_id = operator_review.get("selected_option_id") or recommended_use_case
        accepted_feature_ids = set(operator_review.get("accepted_feature_ids", []) or [])
        rejected_feature_ids = set(operator_review.get("rejected_feature_ids", []) or [])
        options: list[dict[str, Any]] = []
        for option in recommendation.get("options", []):
            option_id = option.get("option_id", "unknown")
            feature_groups = self._feature_groups_for_option(
                option_id=option_id,
                recommended_path=recommended_path,
                google_preference=user_profile.google_services_preference.value,
                requires_updates=os_goals.requires_reliable_updates,
                prefers_lockdown=os_goals.prefers_lockdown_defaults,
                prefers_battery=os_goals.prefers_long_battery_life,
            )
            included_features = list(feature_groups["included_features"])
            optional_features = list(feature_groups["optional_features"])
            excluded_features = list(feature_groups["excluded_features"])
            if option_id == selected_option_id:
                if accepted_feature_ids:
                    accepted = []
                    for item in included_features + optional_features:
                        if item.get("id") in accepted_feature_ids:
                            accepted.append(item)
                    included_features = accepted or included_features
                    optional_features = [item for item in optional_features if item.get("id") not in accepted_feature_ids]
                if rejected_feature_ids:
                    excluded_features.extend(
                        item for item in included_features + optional_features if item.get("id") in rejected_feature_ids
                    )
                    included_features = [item for item in included_features if item.get("id") not in rejected_feature_ids]
                    optional_features = [item for item in optional_features if item.get("id") not in rejected_feature_ids]
            options.append(
                {
                    "option_id": option_id,
                    "label": option.get("label", "Unknown option"),
                    "fit_score": float(option.get("fit_score", 0.0)),
                    "rationale": option.get("rationale", ""),
                    "constraints": option.get("constraints", []),
                    "evidence": option.get("evidence", []),
                    "proposed_os_name": self._proposal_os_name(option_id, recommended_path),
                    "included_features": included_features,
                    "optional_features": optional_features,
                    "excluded_features": excluded_features,
                }
            )
        selected = next((option for option in options if option["option_id"] == selected_option_id), None)
        if not selected and options:
            selected = options[0]
        recommended = next((option for option in options if option["option_id"] == recommended_use_case), None)
        if not recommended:
            recommended = selected
        return {
            "recommended_use_case": recommended_use_case,
            "recommended_path": recommended_path,
            "proposed_os_name": self._proposal_os_name(recommended["option_id"], recommended_path) if recommended else self._proposal_os_name(recommended_use_case, recommended_path),
            "preview_status": preview_execution.status,
            "preview_mode": preview_execution.mode,
            "proposal_summary": self._proposal_summary(recommended_path, recommended["option_id"] if recommended else recommended_use_case),
            "options": options,
            "selected_option_id": selected["option_id"] if selected else selected_option_id,
            "selected_option": selected or {},
        }

    def _proposal_summary(self, recommended_path: str, recommended_use_case: str) -> str:
        option_name = recommended_use_case.replace("_", " ")
        if recommended_path == "research_only_path":
            return (
                f"ForgeOS is presenting a concept proposal for {option_name} while transport, preview, and install readiness continue to mature."
            )
        if recommended_path in {"hardened_stock_path", "maintainable_hardened_path"}:
            return f"ForgeOS is proposing a hardened stock-derived build for {option_name} with rollback visibility preserved."
        if recommended_path in {"aftermarket_path", "managed_family_path", "device_specific_path"}:
            return f"ForgeOS is proposing a customized build track for {option_name}, still subject to preview and verification review."
        return f"ForgeOS is proposing a reviewable build direction for {option_name}."

    def _proposal_os_name(self, option_id: str, recommended_path: str) -> str:
        option_name = option_id.replace("_", " ").strip().title() if option_id else "Unknown Option"
        if recommended_path == "research_only_path":
            return f"{option_name} concept on a hardened stock Android baseline"
        if recommended_path in {"hardened_stock_path", "maintainable_hardened_path"}:
            return f"Hardened stock Android for {option_name}"
        if recommended_path == "aftermarket_path":
            return f"Aftermarket Android build for {option_name}"
        if recommended_path == "managed_family_path":
            return f"Managed family build for {option_name}"
        if recommended_path == "device_specific_path":
            return f"Device-specific tuned build for {option_name}"
        return f"{option_name} build on {recommended_path.replace('_', ' ')}"

    def _feature_groups_for_option(
        self,
        *,
        option_id: str,
        recommended_path: str,
        google_preference: str,
        requires_updates: bool,
        prefers_lockdown: bool,
        prefers_battery: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        included_map: dict[str, list[dict[str, str]]] = {
            "accessibility_focused_phone": [
                {"id": "simple_launcher", "label": "Simplified launcher and larger touch targets", "reason": "Supports low-complexity daily use."},
                {"id": "trusted_contacts", "label": "Trusted-contact shortcuts", "reason": "Keeps key actions close at hand."},
                {"id": "accessibility_toggles", "label": "Accessibility quick toggles", "reason": "Reduces setup friction for assisted use."},
            ],
            "lightweight_custom_android": [
                {"id": "debloated_apps", "label": "Debloated app set", "reason": "Keeps the device lighter and easier to maintain."},
                {"id": "focused_home", "label": "Focused home screen", "reason": "Reduces distractions and clutter."},
                {"id": "recovery_entry", "label": "Visible restore and recovery entry point", "reason": "Preserves reversibility."},
            ],
            "media_device": [
                {"id": "offline_media", "label": "Offline media playback shell", "reason": "Matches the recommended use case."},
                {"id": "large_controls", "label": "Large playback and volume controls", "reason": "Improves clarity for shared-device use."},
            ],
            "home_control_panel": [
                {"id": "kiosk_mode", "label": "Single-purpose kiosk shell", "reason": "Keeps the device task-specific."},
                {"id": "control_tiles", "label": "Large control tiles", "reason": "Improves wall-panel usability."},
            ],
        }
        optional_features = [
            {"id": "operator_notes", "label": "Pinned operator notes in the setup flow", "reason": "Helps explain the rehabilitation choices."},
        ]
        included = list(included_map.get(option_id, []))
        excluded = [
            {"id": "wipe_autostart", "label": "Automatic wipe/install start", "reason": "Destructive execution must stay operator-gated."},
        ]
        if google_preference == "keep_google_services":
            included.append({"id": "google_services", "label": "Keep Google services compatibility", "reason": "Matches the selected service preference."})
        elif google_preference == "reduce_google_services":
            optional_features.append({"id": "reduced_google", "label": "Reduce Google services footprint", "reason": "Can be accepted or rejected by the operator."})
        else:
            included.append({"id": "minimize_google", "label": "Remove Google services where feasible", "reason": "Matches the selected service preference."})
            excluded.append({"id": "full_google_bundle", "label": "Full Google bundle", "reason": "Excluded by the selected Google-services preference."})
        if requires_updates:
            included.append({"id": "update_channel", "label": "Preserve a reliable update path", "reason": "Matches the stated restore and maintenance requirements."})
        else:
            optional_features.append({"id": "manual_updates", "label": "Manual update workflow", "reason": "Allowed because reliable updates are not mandatory."})
        if prefers_lockdown:
            included.append({"id": "lockdown_defaults", "label": "Hardened privacy and lockdown defaults", "reason": "Matches the safety-first profile."})
        if prefers_battery:
            included.append({"id": "battery_profile", "label": "Battery-preserving runtime tuning", "reason": "Matches the long-battery-life preference."})
        if recommended_path == "research_only_path":
            excluded.append({"id": "emulator_validated_build", "label": "Emulator-validated install artifact", "reason": "Not available yet while the session remains in research mode."})
        return {
            "included_features": included,
            "optional_features": optional_features,
            "excluded_features": excluded,
        }

    def _read_operator_review(self, session_dir: Path) -> dict[str, Any]:
        path = session_dir / "runtime" / "operator-review.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _phase_for_state(
        self,
        state: SessionState,
        *,
        assessment: dict[str, Any],
        build_plan: dict[str, Any],
        backup_plan: dict[str, Any],
        install_gate: ApprovalGate,
        preview_execution: PreviewExecution,
        verification_execution: VerificationExecution,
    ) -> RuntimePhase:
        direct_phase = STATE_TO_PHASE.get(state.state)
        if direct_phase and direct_phase not in {RuntimePhase.BLOCKED, RuntimePhase.DISCOVERY}:
            return direct_phase

        support_status = assessment.get("support_status", "unknown")
        recommended_path = build_plan.get("os_path", "research_only_path")
        backup_ready = bool(backup_plan.get("backup_bundle_path"))

        if support_status == "blocked":
            return RuntimePhase.BLOCKED
        if recommended_path == "research_only_path" or support_status == "research_only":
            return RuntimePhase.RECOMMENDATION
        if not backup_ready:
            return RuntimePhase.BACKUP
        if preview_execution.status != "executed":
            return RuntimePhase.PREVIEW
        if verification_execution.status != "executed":
            return RuntimePhase.VERIFICATION
        if install_gate.missing_requirements or not install_gate.allowed:
            return RuntimePhase.VERIFICATION
        return RuntimePhase.INSTALL

    def _operator_summary(
        self,
        assessment: dict[str, Any],
        build_plan: dict[str, Any],
        blocker: dict[str, Any],
        install_gate: ApprovalGate,
    ) -> str:
        if build_plan.get("os_path") == "research_only_path" or assessment.get("support_status") == "research_only":
            return "ForgeOS is still researching the safest attainable path. Wipe and rebuild remain deferred until transport, feasibility, and restore confidence improve."
        if blocker.get("blocker_type") and blocker.get("blocker_type") != "none":
            return blocker.get("summary", assessment.get("summary", "ForgeOS is gathering more evidence."))
        if not install_gate.allowed:
            return "ForgeOS has a candidate plan, but destructive execution remains behind deterministic safety gates."
        return assessment.get("summary", "ForgeOS is ready to continue the rehabilitation flow.")

    def _options_from_recommendation(self, recommendation: dict[str, Any]) -> list[RecommendationOption]:
        options = []
        for option in recommendation.get("options", []):
            options.append(
                RecommendationOption(
                    option_id=option.get("option_id", "unknown"),
                    label=option.get("label", "Unknown option"),
                    fit_score=float(option.get("fit_score", 0.0)),
                    rationale=option.get("rationale", ""),
                    constraints=option.get("constraints", []),
                    evidence=option.get("evidence", []),
                )
            )
        return options

    def _evidence_paths(self, session_dir: Path) -> list[str]:
        candidates = [
            session_dir / "device-profile.json",
            session_dir / "session-state.json",
            session_dir / "reports" / "assessment.json",
            session_dir / "reports" / "engagement.json",
            session_dir / "backup" / "backup-plan.json",
            session_dir / "restore" / "restore-plan.json",
            session_dir / "execution" / "flash-plan.json",
            session_dir / "runtime" / "adapter-health.json",
            session_dir / "runtime" / "preview" / "preview-execution.json",
            session_dir / "runtime" / "verification" / "verification-execution.json",
        ]
        return [str(path) for path in candidates if path.exists()]

    def _next_actions(self, blocker: dict[str, Any], install_gate: ApprovalGate) -> list[str]:
        if blocker.get("machine_solvable"):
            return [
                "Continue local remediation through the routed worker.",
                "Validate the result and retry locally if the failure is recoverable.",
            ]
        actions = list(blocker.get("user_steps", []))
        if install_gate.missing_requirements:
            actions.extend(install_gate.missing_requirements)
        return actions[:6]

    def _hard_stops(self, blocker: dict[str, Any], install_gate: ApprovalGate) -> list[str]:
        hard_stops = []
        if not blocker.get("machine_solvable") and blocker.get("blocker_type") != "none":
            hard_stops.append(blocker.get("summary", "External action is required."))
        if install_gate.missing_requirements:
            hard_stops.extend(install_gate.missing_requirements)
        return hard_stops

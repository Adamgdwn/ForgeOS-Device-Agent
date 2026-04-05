from __future__ import annotations

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
    ) -> dict[str, str]:
        plan = RuntimeSessionPlan(
            session_id=state.session_id,
            phase=self._phase_for_state(state),
            mission="Rehabilitate this device into a safe, useful, restorable system with the least-risk path available.",
            operator_summary=self._operator_summary(assessment, blocker, install_gate),
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
                    },
                )
            ),
        }
        return files

    def _phase_for_state(self, state: SessionState) -> RuntimePhase:
        return STATE_TO_PHASE.get(state.state, RuntimePhase.BLOCKED if state.current_blocker_type else RuntimePhase.DISCOVERY)

    def _operator_summary(
        self,
        assessment: dict[str, Any],
        blocker: dict[str, Any],
        install_gate: ApprovalGate,
    ) -> str:
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

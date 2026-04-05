from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.codex_handoff import CodexHandoffEngine
from app.core.codegen_runtime import CodegenRuntime
from app.core.connection_engine import ConnectionEngine
from app.core.knowledge import KnowledgeEngine
from app.core.knowledge_lookup import KnowledgeLookup
from app.core.patch_executor import PatchExecutor
from app.core.reporting import ReportWriter
from app.core.policy import PolicyEngine
from app.core.promotion import PromotionEngine
from app.core.retry_planner import RetryPlanner
from app.core.session_manager import SessionManager
from app.core.state_machine import is_transition_allowed
from app.tools.autonomous_engagement import AutonomousEngagementTool
from app.tools.build_resolver import BuildResolverTool
from app.tools.device_probe import DeviceProbeTool
from app.tools.feasibility_assessor import FeasibilityAssessorTool
from app.tools.flash_executor import FlashExecutorTool
from app.tools.strategy_selector import BuildStrategySelectorTool
from app.tools.vscode_opener import VSCodeOpenerTool
from app.core.blocker_engine import BlockerEngine


class ForgeOrchestrator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sessions = SessionManager(root)
        self.reports = ReportWriter(root / "output")
        self.policy = PolicyEngine(root / "master" / "policies" / "default_policy.json").load()
        self.blockers = BlockerEngine(root)
        self.codegen_runtime = CodegenRuntime(root)
        self.codex_handoff = CodexHandoffEngine(root)
        self.connection_engine = ConnectionEngine(root)
        self.knowledge = KnowledgeEngine(root)
        self.knowledge_lookup = KnowledgeLookup(root)
        self.patch_executor = PatchExecutor(root)
        self.promotion = PromotionEngine(root)
        self.retry_planner = RetryPlanner(root)
        self.device_probe = DeviceProbeTool(root)
        self.assessor = FeasibilityAssessorTool(root)
        self.build_resolver = BuildResolverTool(root)
        self.strategy_selector = BuildStrategySelectorTool(root)
        self.autonomous_engagement = AutonomousEngagementTool(root)
        self.flash_executor = FlashExecutorTool(root)
        self.vscode_opener = VSCodeOpenerTool(root)

    def handle_device_event(self, event: dict[str, Any]) -> Path:
        probe_result = self.device_probe.execute({"event": event})
        session_dir = self.sessions.create_or_resume(probe_result["device"])
        self._safe_transition(session_dir, "PROFILE_SYNTHESIS", "Device profile synthesis started")
        assessment = self.assessor.execute({"device": probe_result["device"], "session_dir": str(session_dir)})
        self.sessions.annotate(session_dir, assessment["summary"])
        engagement = self.autonomous_engagement.execute(
            {"device": probe_result["device"], "session_dir": str(session_dir)}
        )
        self.sessions.annotate(session_dir, engagement["summary"])
        state = self.sessions.load_session_state(session_dir)
        self._safe_transition(session_dir, "MATCH_MASTER", "Matching master framework and prior knowledge")
        user_profile = self.sessions.load_user_profile(session_dir)
        os_goals = self.sessions.load_os_goals(session_dir)

        if assessment["support_status"] == "blocked":
            if is_transition_allowed(state.state, state.state.__class__.BLOCKED):
                self.sessions.transition(session_dir, state.state.__class__.BLOCKED, assessment["summary"])
        else:
            strategy = self.strategy_selector.execute(
                {
                    "assessment": assessment,
                    "device": probe_result["device"],
                    "user_profile": {
                        "persona": user_profile.persona.value,
                        "technical_comfort": user_profile.technical_comfort.value,
                        "primary_priority": user_profile.primary_priority.value,
                        "google_services_preference": user_profile.google_services_preference.value,
                    },
                    "os_goals": {
                        "top_goal": os_goals.top_goal.value,
                        "secondary_goal": os_goals.secondary_goal.value,
                        "requires_reliable_updates": os_goals.requires_reliable_updates,
                        "prefers_long_battery_life": os_goals.prefers_long_battery_life,
                        "prefers_lockdown_defaults": os_goals.prefers_lockdown_defaults,
                    },
                }
            )
            updated = self.sessions.load_session_state(session_dir)
            updated.selected_strategy = strategy["strategy_id"]
            updated.support_status = updated.support_status.__class__(assessment["support_status"])
            self.sessions.write_session_state(session_dir, updated)
            self._safe_transition(session_dir, "PATH_SELECT", f"Selected strategy {strategy['strategy_id']}")

        current_profile = self.sessions.load_device_profile(session_dir)
        current_state = self.sessions.load_session_state(session_dir)
        knowledge_match = self.knowledge_lookup.lookup(current_profile.manufacturer, current_profile.model)
        connection_plan = self.connection_engine.build_plan(
            current_profile,
            current_state,
            assessment,
            engagement,
        )
        connection_plan_path = self.connection_engine.write_plan(session_dir, connection_plan)
        self._safe_transition(session_dir, "BLOCKER_CLASSIFY", "Classifying current blocker state")
        blocker = self.blockers.classify(
            current_profile,
            current_state,
            assessment,
            engagement,
            connection_plan,
        )
        blocker_path = self.blockers.write(session_dir, blocker)
        build_plan = self.build_resolver.execute(
            {
                "assessment": assessment,
                "connection_plan": connection_plan,
                "selected_strategy": current_state.selected_strategy or "research_only",
                "user_profile": {
                    "persona": user_profile.persona.value,
                    "technical_comfort": user_profile.technical_comfort.value,
                    "primary_priority": user_profile.primary_priority.value,
                    "google_services_preference": user_profile.google_services_preference.value,
                },
                "os_goals": {
                    "top_goal": os_goals.top_goal.value,
                    "secondary_goal": os_goals.secondary_goal.value,
                    "requires_reliable_updates": os_goals.requires_reliable_updates,
                    "prefers_long_battery_life": os_goals.prefers_long_battery_life,
                    "prefers_lockdown_defaults": os_goals.prefers_lockdown_defaults,
                },
            }
        )
        flash_plan = self.flash_executor.build_plan(
            session_id=current_state.session_id,
            device={
                "transport": current_profile.transport.value,
                "manufacturer": current_profile.manufacturer,
                "model": current_profile.model,
                "serial": current_profile.serial,
            },
            assessment=assessment,
            build_plan=build_plan,
            policy=self.policy,
            live_mode=False,
        )
        flash_plan_path = self.sessions.write_flash_plan(session_dir, flash_plan)
        generated_runtime = {}
        patch_result = {}
        retry_plan = {}
        if blocker.get("machine_solvable"):
            self._safe_transition(session_dir, "CODEGEN_TASK", "Generating session-local runtime artifacts")
            generated_runtime = self.codegen_runtime.generate(session_dir, blocker, connection_plan, build_plan)
            self._safe_transition(session_dir, "PATCH_APPLY", "Registering generated runtime artifacts")
            patch_result = self.patch_executor.apply(session_dir, generated_runtime)
            self._safe_transition(session_dir, "EXECUTE_STEP", "Prepared next autonomous execution step")
        else:
            self._safe_transition(session_dir, "QUESTION_GATE", "Waiting for minimum required external action")
        retry_plan = self.retry_planner.build_plan(blocker, generated_runtime or None)
        retry_plan_path = self.retry_planner.write(session_dir, retry_plan)
        handoff_files: dict[str, str] = {}
        if self.policy.enable_codex_handoff:
            handoff_files = self.codex_handoff.prepare(
                session_dir,
                current_profile,
                current_state,
                user_profile,
                os_goals,
                assessment,
                engagement,
                connection_plan,
                blocker,
                build_plan,
                knowledge_match,
            )
            if self.policy.open_vscode_on_session_create:
                self.vscode_opener.execute(
                    {"target_path": handoff_files["workspace_file"], "new_window": True}
                )
        learning_summary = self.knowledge.record_session_outcome(
            current_profile,
            current_state,
            assessment,
        )
        support_matrix = self.knowledge.rebuild_support_matrix()
        promotion_candidates = self.promotion.evaluate(support_matrix)

        self.reports.write_session_report(
            session_dir,
            report_type="assessment",
            status=assessment["support_status"],
            summary=assessment["summary"],
            details={
                "event": event,
                "assessment": assessment,
                "engagement": engagement,
                "knowledge_match": knowledge_match,
                "user_profile": {
                    "persona": user_profile.persona.value,
                    "technical_comfort": user_profile.technical_comfort.value,
                    "primary_priority": user_profile.primary_priority.value,
                    "google_services_preference": user_profile.google_services_preference.value,
                },
                "os_goals": {
                    "top_goal": os_goals.top_goal.value,
                    "secondary_goal": os_goals.secondary_goal.value,
                    "requires_reliable_updates": os_goals.requires_reliable_updates,
                    "prefers_long_battery_life": os_goals.prefers_long_battery_life,
                    "prefers_lockdown_defaults": os_goals.prefers_lockdown_defaults,
                },
                "blocker": blocker,
                "build_plan": build_plan,
                "flash_plan_path": str(flash_plan_path),
            },
        )
        self.reports.write_session_report(
            session_dir,
            report_type="engagement",
            status=engagement["engagement_status"],
            summary=engagement["summary"],
            details=engagement,
        )
        self.reports.write_session_report(
            session_dir,
            report_type="learning",
            status="ok",
            summary="Knowledge base and support matrix updated for this device session.",
            details={
                "learning_summary": learning_summary,
                "promotion_candidate_count": len(promotion_candidates.get("candidates", [])),
            },
        )
        self.reports.write_session_report(
            session_dir,
            report_type="blocker",
            status=blocker["blocker_type"],
            summary=blocker["summary"],
            details=blocker,
        )
        self.reports.write_session_report(
            session_dir,
            report_type="build_plan",
            status="ready",
            summary=build_plan["reason"],
            details=build_plan,
        )
        self.reports.write_session_report(
            session_dir,
            report_type="flash_plan",
            status=flash_plan.status,
            summary=flash_plan.summary,
            details={
                "build_path": flash_plan.build_path,
                "dry_run": flash_plan.dry_run,
                "requires_unlock": flash_plan.requires_unlock,
                "requires_wipe": flash_plan.requires_wipe,
                "restore_path_available": flash_plan.restore_path_available,
                "transport": flash_plan.transport,
                "step_count": flash_plan.step_count,
                "steps": flash_plan.steps,
                "artifact_hints": flash_plan.artifact_hints,
            },
        )
        self.reports.write_session_report(
            session_dir,
            report_type="execution_queue",
            status=retry_plan["action"],
            summary=retry_plan["rationale"],
            details={
                "retry_plan": retry_plan,
                "generated_runtime": generated_runtime,
                "patch_result": patch_result,
                "knowledge_match": knowledge_match,
            },
        )
        self.reports.write_session_report(
            session_dir,
            report_type="codex_handoff",
            status="ready" if handoff_files else "disabled",
            summary="Prepared VS Code workspace and Codex task brief for this device session.",
            details={
                "handoff_files": handoff_files,
                "connection_plan_path": str(connection_plan_path),
                "blocker_path": str(blocker_path),
                "retry_plan_path": str(retry_plan_path),
                "recommended_adapter": connection_plan.get("recommended_adapter"),
                "recommended_strategy": current_state.selected_strategy,
                "build_plan": build_plan,
                "flash_plan_path": str(flash_plan_path),
            },
        )
        self.logger.info("Handled device event for session %s", session_dir.name)
        return session_dir

    def record_wipe_approval(
        self,
        session_dir: Path,
        approved: bool,
        confirmation_phrase: str,
        restore_path_confirmed: bool,
        notes: str = "",
        approval_scope: str = "full_wipe_and_rebuild",
    ) -> Path:
        approval = self.sessions.load_destructive_approval(session_dir)
        approval.approved = approved
        approval.approval_scope = approval_scope if approved else "none"
        approval.confirmation_phrase = confirmation_phrase
        approval.consequences_acknowledged = approved
        approval.restore_path_confirmed = restore_path_confirmed
        approval.notes = notes
        approval.approved_at = approval.updated_at if approved else None
        approval_path = self.sessions.write_destructive_approval(session_dir, approval)

        state = self.sessions.load_session_state(session_dir)
        state.destructive_actions_approved = approved
        self.sessions.write_session_state(session_dir, state)
        self.reports.write_session_report(
            session_dir,
            report_type="approval_gate",
            status="approved" if approved else "not_approved",
            summary=(
                "Operator granted explicit wipe-and-rebuild permission."
                if approved
                else "Operator approval for destructive actions has not been granted."
            ),
            details={
                "approval_path": str(approval_path),
                "approval_scope": approval.approval_scope,
                "restore_path_confirmed": approval.restore_path_confirmed,
                "confirmation_phrase_ok": approval.confirmation_phrase == "WIPE_AND_REBUILD",
            },
        )
        return approval_path

    def execute_approved_flash(self, session_dir: Path, live_mode: bool = False) -> dict[str, Any]:
        flash_plan = self.sessions.load_flash_plan(session_dir)
        if flash_plan is None:
            raise ValueError(f"No flash plan exists for session {session_dir.name}")
        approval = self.sessions.load_destructive_approval(session_dir)
        result = self.flash_executor.execute(
            {
                "flash_plan": {
                    "session_id": flash_plan.session_id,
                    "build_path": flash_plan.build_path,
                    "dry_run": not live_mode,
                    "requires_unlock": flash_plan.requires_unlock,
                    "requires_wipe": flash_plan.requires_wipe,
                    "restore_path_available": flash_plan.restore_path_available,
                    "transport": flash_plan.transport,
                    "step_count": flash_plan.step_count,
                    "steps": flash_plan.steps,
                    "artifact_hints": flash_plan.artifact_hints,
                    "status": flash_plan.status,
                    "summary": flash_plan.summary,
                    "generated_at": flash_plan.generated_at,
                    "updated_at": flash_plan.updated_at,
                },
                "approval": {
                    "session_id": approval.session_id,
                    "approved": approval.approved,
                    "approval_scope": approval.approval_scope,
                    "confirmation_phrase": approval.confirmation_phrase,
                    "approved_by": approval.approved_by,
                    "consequences_acknowledged": approval.consequences_acknowledged,
                    "restore_path_confirmed": approval.restore_path_confirmed,
                    "notes": approval.notes,
                    "approved_at": approval.approved_at,
                    "updated_at": approval.updated_at,
                },
                "policy": {
                    "policy_version": self.policy.policy_version,
                    "default_dry_run": self.policy.default_dry_run,
                    "require_restore_path": self.policy.require_restore_path,
                    "allow_live_destructive_actions": self.policy.allow_live_destructive_actions,
                    "require_explicit_wipe_phrase": self.policy.require_explicit_wipe_phrase,
                    "allow_bootloader_relock": self.policy.allow_bootloader_relock,
                    "open_vscode_on_launch": self.policy.open_vscode_on_launch,
                    "open_vscode_on_session_create": self.policy.open_vscode_on_session_create,
                    "enable_codex_handoff": self.policy.enable_codex_handoff,
                    "priority_order": self.policy.priority_order,
                    "host_requirements": self.policy.host_requirements,
                },
                "device": {
                    "serial": self.sessions.load_device_profile(session_dir).serial,
                },
                "session_dir": str(session_dir),
            },
            dry_run=not live_mode,
        )
        if result["status"] in {"dry_run_complete", "live_execution_queued"}:
            self._safe_transition(session_dir, "FLASH_PREP", "Prepared approved flash execution")
            self._safe_transition(session_dir, "FLASH", "Recorded approved flash execution")
        self.reports.write_session_report(
            session_dir,
            report_type="flash_execution",
            status=result["status"],
            summary=result["summary"],
            details=result["details"],
        )
        return result

    def _safe_transition(self, session_dir: Path, target_name: str, reason: str) -> None:
        state = self.sessions.load_session_state(session_dir)
        target = state.state.__class__[target_name]
        if is_transition_allowed(state.state, target):
            self.sessions.transition(session_dir, target, reason)

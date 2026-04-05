from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.codex_handoff import CodexHandoffEngine
from app.core.codegen_runtime import CodegenRuntime
from app.core.connection_engine import ConnectionEngine
from app.core.knowledge import KnowledgeEngine
from app.core.knowledge_lookup import KnowledgeLookup
from app.core.policy_guard import PolicyGuard
from app.core.patch_executor import PatchExecutor
from app.core.reporting import ReportWriter
from app.core.policy import PolicyEngine
from app.core.promotion import PromotionEngine
from app.core.retry_planner import RetryPlanner
from app.core.runtime_pipelines import PreviewPipeline, VerificationPipeline
from app.core.runtime_planner import RuntimePlanner
from app.core.runtime_workers import WorkerRegistry, WorkerRouter, WorkerRuntime, WorkerTask
from app.core.session_manager import SessionManager
from app.core.state_machine import is_transition_allowed
from app.core.models import TaskRisk, to_dict
from app.tools.autonomous_engagement import AutonomousEngagementTool
from app.tools.backup_restore import BackupAndRestorePlannerTool
from app.tools.build_resolver import BuildResolverTool
from app.tools.device_probe import DeviceProbeTool
from app.tools.feasibility_assessor import FeasibilityAssessorTool
from app.tools.flash_executor import FlashExecutorTool
from app.tools.restore_controller import RestoreControllerTool
from app.tools.strategy_selector import BuildStrategySelectorTool
from app.tools.use_case_recommender import UseCaseRecommenderTool
from app.tools.vscode_opener import VSCodeOpenerTool
from app.core.blocker_engine import BlockerEngine

MANAGEABLE_TRANSPORTS = {"usb-adb", "usb-fastboot", "usb-fastbootd", "usb-recovery"}


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
        self.policy_guard = PolicyGuard(root)
        self.device_probe = DeviceProbeTool(root)
        self.assessor = FeasibilityAssessorTool(root)
        self.build_resolver = BuildResolverTool(root)
        self.strategy_selector = BuildStrategySelectorTool(root)
        self.use_case_recommender = UseCaseRecommenderTool(root)
        self.autonomous_engagement = AutonomousEngagementTool(root)
        self.backup_restore = BackupAndRestorePlannerTool(root)
        self.flash_executor = FlashExecutorTool(root)
        self.restore_controller = RestoreControllerTool(root)
        self.vscode_opener = VSCodeOpenerTool(root)
        self.worker_registry = WorkerRegistry(root).discover()
        self.worker_router = WorkerRouter(self.worker_registry)
        self.worker_runtime = WorkerRuntime(root, self.worker_registry)
        self.preview_pipeline = PreviewPipeline(root)
        self.verification_pipeline = VerificationPipeline(root)
        self.runtime_planner = RuntimePlanner(root, self.sessions)

    def handle_device_event(self, event: dict[str, Any]) -> Path:
        probe_result = self.device_probe.execute({"event": event})
        session_dir = self.sessions.create_or_resume(probe_result["device"])
        self._safe_transition(session_dir, "DEVICE_ATTACHED", "Device attachment event received")
        self._safe_transition(session_dir, "DISCOVER", "Runtime discovery started")
        self._safe_transition(session_dir, "PROFILE_SYNTHESIS", "Device profile synthesis started")

        device_payload = probe_result["device"]
        self._safe_transition(session_dir, "ASSESS", "Device assessment started")
        assessment = self.assessor.execute({"device": device_payload, "session_dir": str(session_dir)})
        self.sessions.annotate(session_dir, assessment["summary"])
        engagement = self.autonomous_engagement.execute(
            {"device": device_payload, "session_dir": str(session_dir)}
        )
        self.sessions.annotate(session_dir, engagement["summary"])
        self._safe_transition(session_dir, "MATCH_MASTER", "Matching master framework and prior knowledge")
        user_profile = self.sessions.load_user_profile(session_dir)
        os_goals = self.sessions.load_os_goals(session_dir)
        self._safe_transition(session_dir, "BACKUP_PLAN", "Entering safety-first backup and restore planning")
        current_state = self.sessions.load_session_state(session_dir)
        if assessment["support_status"] == "blocked":
            if is_transition_allowed(current_state.state, current_state.state.__class__.BLOCKED):
                self.sessions.transition(session_dir, current_state.state.__class__.BLOCKED, assessment["summary"])
        else:
            strategy = self.strategy_selector.execute(
                {
                    "assessment": assessment,
                    "device": device_payload,
                    "user_profile": {
                        "persona": user_profile.persona.value,
                        "technical_comfort": user_profile.technical_comfort.value,
                        "primary_priority": user_profile.primary_priority.value,
                        "google_services_preference": user_profile.google_services_preference.value,
                        "autonomy_limit": user_profile.autonomy_limit.value,
                        "risk_tolerance": user_profile.risk_tolerance.value,
                        "restore_expectation": user_profile.restore_expectation.value,
                        "target_use_case": user_profile.target_use_case.value,
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

        runtime_result = self._run_runtime_cycle(
            session_dir=session_dir,
            device_payload=device_payload,
            assessment=assessment,
            engagement=engagement,
            user_profile=user_profile,
            os_goals=os_goals,
        )

        current_profile = runtime_result["profile"]
        current_state = runtime_result["state"]
        assessment = runtime_result["assessment"]
        engagement = runtime_result["engagement"]
        knowledge_match = runtime_result["knowledge_match"]
        connection_plan = runtime_result["connection_plan"]
        blocker = runtime_result["blocker"]
        build_plan = runtime_result["build_plan"]
        backup_plan = runtime_result["backup_plan"]
        restore_plan = runtime_result["restore_plan"]
        flash_plan = runtime_result["flash_plan"]
        generated_runtime = runtime_result["generated_runtime"]
        patch_result = runtime_result["patch_result"]
        execution_result = runtime_result["execution_result"]
        inspection = runtime_result["inspection"]
        retry_plan = runtime_result["retry_plan"]

        connection_plan_path = self.connection_engine.write_plan(session_dir, connection_plan)
        blocker_path = self.blockers.write(session_dir, blocker)
        flash_plan_path = self.sessions.write_flash_plan(session_dir, flash_plan)
        retry_plan_path = self.retry_planner.write(session_dir, retry_plan)
        runtime_files = runtime_result["runtime_files"]
        recommendation = runtime_result["recommendation"]
        worker_routes = runtime_result["worker_routes"]
        install_gate = runtime_result["install_gate"]
        runtime_gate = runtime_result["runtime_gate"]
        worker_executions = runtime_result["worker_executions"]
        preview_execution = runtime_result["preview_execution"]
        verification_execution = runtime_result["verification_execution"]

        if self.policy.open_vscode_on_session_create:
            self.vscode_opener.execute(
                {"target_path": str(session_dir), "new_window": True}
            )
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
                    "autonomy_limit": user_profile.autonomy_limit.value,
                    "risk_tolerance": user_profile.risk_tolerance.value,
                    "restore_expectation": user_profile.restore_expectation.value,
                    "target_use_case": user_profile.target_use_case.value,
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
                "backup_plan": backup_plan["plan"],
                "restore_plan_path": restore_plan["restore_plan_path"],
                "inspection": inspection,
                "recommendation": recommendation,
                "runtime_files": runtime_files,
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
            report_type="backup_plan",
            status="captured" if backup_plan["restore_path_feasible"] else "limited",
            summary=backup_plan["plan"]["summary"],
            details=backup_plan["plan"],
        )
        self.reports.write_session_report(
            session_dir,
            report_type="restore_plan",
            status=restore_plan["status"],
            summary=restore_plan["summary"],
            details=restore_plan["details"],
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
                "execution_result": execution_result,
                "inspection": inspection,
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
                "backup_bundle_path": backup_plan["plan"]["backup_bundle_path"],
                "runtime_plan_path": runtime_files["runtime_plan_path"],
            },
        )
        self.reports.write_session_report(
            session_dir,
            report_type="runtime",
            status=runtime_gate.action,
            summary="ForgeOS updated the runtime session plan, worker routing, and approval gates.",
            details={
                "runtime_files": runtime_files,
                "worker_routes": [to_dict(route) for route in worker_routes],
                "worker_executions": [to_dict(execution) for execution in worker_executions],
                "recommendation": recommendation,
                "install_gate": to_dict(install_gate),
                "runtime_gate": to_dict(runtime_gate),
                "preview_execution": to_dict(preview_execution),
                "verification_execution": to_dict(verification_execution),
                "worker_inventory": self.worker_registry.inventory(),
            },
        )
        self.logger.info("Handled device event for session %s", session_dir.name)
        return session_dir

    def recompute_session_runtime(self, session_dir: Path, *, lightweight: bool = False) -> dict[str, Any]:
        profile = self.sessions.load_device_profile(session_dir)
        user_profile = self.sessions.load_user_profile(session_dir)
        os_goals = self.sessions.load_os_goals(session_dir)
        assessment_report = self._load_report_details(session_dir, "assessment")
        engagement_report = self._load_report_details(session_dir, "engagement")
        assessment = assessment_report.get("assessment", {}) or {
            "support_status": self.sessions.load_session_state(session_dir).support_status.value,
            "summary": "ForgeOS is recomputing the runtime with the updated profile.",
            "recommended_path": "research_only_path",
            "restore_path_feasible": False,
        }
        engagement = {
            "engagement_status": engagement_report.get("engagement_status", engagement_report.get("status", "unknown")),
            "summary": engagement_report.get("summary", "No engagement summary available."),
            **engagement_report,
        }
        device_payload = {
            "manufacturer": profile.manufacturer,
            "model": profile.model,
            "serial": profile.serial,
            "android_version": profile.android_version,
            "bootloader_locked": profile.bootloader_locked,
            "verified_boot_state": profile.verified_boot_state,
            "slot_info": profile.slot_info or {},
            "battery": profile.battery or {},
            "transport": profile.transport,
            "device_codename": profile.device_codename,
            "raw_event": profile.raw_probe_data.get("raw_event", profile.raw_probe_data),
        }
        runtime_result = self._run_runtime_cycle(
            session_dir=session_dir,
            device_payload=device_payload,
            assessment=assessment,
            engagement=engagement,
            user_profile=user_profile,
            os_goals=os_goals,
            execute_workers=not lightweight,
            execute_runtime_pipelines=not lightweight,
        )
        self.connection_engine.write_plan(session_dir, runtime_result["connection_plan"])
        self.blockers.write(session_dir, runtime_result["blocker"])
        self.sessions.write_flash_plan(session_dir, runtime_result["flash_plan"])
        self.retry_planner.write(session_dir, runtime_result["retry_plan"])
        self.reports.write_session_report(
            session_dir,
            report_type="build_plan",
            status="ready",
            summary=runtime_result["build_plan"]["reason"],
            details=runtime_result["build_plan"],
        )
        self.reports.write_session_report(
            session_dir,
            report_type="runtime",
            status=runtime_result["runtime_gate"].action,
            summary=(
                "ForgeOS recomputed the runtime after profile or session updates."
                if not lightweight
                else "ForgeOS refreshed the runtime plan in lightweight GUI mode without worker execution."
            ),
            details={
                "runtime_files": runtime_result["runtime_files"],
                "worker_routes": [to_dict(route) for route in runtime_result["worker_routes"]],
                "worker_executions": [to_dict(execution) for execution in runtime_result["worker_executions"]],
                "recommendation": runtime_result["recommendation"],
                "install_gate": to_dict(runtime_result["install_gate"]),
                "runtime_gate": to_dict(runtime_result["runtime_gate"]),
                "preview_execution": to_dict(runtime_result["preview_execution"]),
                "verification_execution": to_dict(runtime_result["verification_execution"]),
                "worker_inventory": self.worker_registry.inventory(),
            },
        )
        return runtime_result

    def _run_runtime_cycle(
        self,
        session_dir: Path,
        device_payload: dict[str, Any],
        assessment: dict[str, Any],
        engagement: dict[str, Any],
        user_profile: Any,
        os_goals: Any,
        *,
        execute_workers: bool = True,
        execute_runtime_pipelines: bool = True,
    ) -> dict[str, Any]:
        current_profile = self.sessions.load_device_profile(session_dir)
        current_state = self.sessions.load_session_state(session_dir)
        knowledge_match = self.knowledge_lookup.lookup(current_profile.manufacturer, current_profile.model)
        connection_plan = self.connection_engine.build_plan(current_profile, current_state, assessment, engagement)
        backup_plan = self.backup_restore.execute(
            {
                "device": device_payload,
                "session_dir": str(session_dir),
                "assessment": assessment,
            }
        )
        restore_plan = self.restore_controller.execute(
            {
                "session_dir": str(session_dir),
                "backup_plan": backup_plan["plan"],
            }
        )
        operator_review = self._read_operator_review(session_dir)
        recommendation = self.use_case_recommender.execute(
            {
                "device": device_payload,
                "assessment": assessment,
                "user_profile": {
                    "persona": user_profile.persona.value,
                    "technical_comfort": user_profile.technical_comfort.value,
                    "primary_priority": user_profile.primary_priority.value,
                    "google_services_preference": user_profile.google_services_preference.value,
                    "autonomy_limit": user_profile.autonomy_limit.value,
                    "risk_tolerance": user_profile.risk_tolerance.value,
                    "restore_expectation": user_profile.restore_expectation.value,
                    "target_use_case": user_profile.target_use_case.value,
                },
                "os_goals": {
                    "top_goal": os_goals.top_goal.value,
                    "secondary_goal": os_goals.secondary_goal.value,
                    "requires_reliable_updates": os_goals.requires_reliable_updates,
                    "prefers_long_battery_life": os_goals.prefers_long_battery_life,
                    "prefers_lockdown_defaults": os_goals.prefers_lockdown_defaults,
                },
                "connection_plan": connection_plan,
            }
        )
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
                    "autonomy_limit": user_profile.autonomy_limit.value,
                    "risk_tolerance": user_profile.risk_tolerance.value,
                    "restore_expectation": user_profile.restore_expectation.value,
                    "target_use_case": user_profile.target_use_case.value,
                },
                "os_goals": {
                    "top_goal": os_goals.top_goal.value,
                    "secondary_goal": os_goals.secondary_goal.value,
                    "requires_reliable_updates": os_goals.requires_reliable_updates,
                    "prefers_long_battery_life": os_goals.prefers_long_battery_life,
                    "prefers_lockdown_defaults": os_goals.prefers_lockdown_defaults,
                },
                "recommendation": recommendation,
                "operator_review": operator_review,
            }
        )
        self._safe_transition(session_dir, "RECOMMEND", "ForgeOS is converting evidence into a recommended use case and build path")
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
            backup_plan=backup_plan["plan"],
            policy=self.policy,
            live_mode=False,
        )
        self._safe_transition(session_dir, "BLOCKER_CLASSIFY", "Classifying blocker state for autonomous continuation")
        blocker = self.blockers.classify(
            current_profile,
            current_state,
            assessment,
            engagement,
            connection_plan,
        )
        current_state = self.sessions.load_session_state(session_dir)
        current_state.current_blocker_type = blocker["blocker_type"]
        current_state.blocker_confidence = blocker["confidence"]
        self.sessions.write_session_state(session_dir, current_state)

        worker_routes = [
            self.worker_router.route(
                WorkerTask(
                    task_type="device_discovery",
                    summary="Interrogate the current device state and collect transport evidence.",
                    prompt=(
                        "Summarize the current device transport evidence and the next safest runtime action.\n\n"
                        f"Assessment: {assessment.get('summary', '')}\n"
                        f"Connection plan: {json_safe(connection_plan)}"
                    ),
                    risk=TaskRisk.LOW,
                    repetitive=True,
                )
            ),
            self.worker_router.route(
                WorkerTask(
                    task_type="use_case_recommendation",
                    summary="Infer the best attainable use case from the device evidence and user goals.",
                    prompt=(
                        "Given the device evidence and user goals, summarize the best attainable device rehabilitation outcome.\n\n"
                        f"Recommendation seed: {json_safe(recommendation)}"
                    ),
                    risk=TaskRisk.MEDIUM,
                )
            ),
        ]
        worker_tasks: list[WorkerTask] = [
            WorkerTask(
                task_type="device_discovery",
                summary="Interrogate the current device state and collect transport evidence.",
                prompt=(
                    "Summarize the current device transport evidence and the next safest runtime action.\n\n"
                    f"Assessment: {assessment.get('summary', '')}\n"
                    f"Connection plan: {json_safe(connection_plan)}"
                ),
                risk=TaskRisk.LOW,
                repetitive=True,
                retry_budget=1,
                context={"assessment": assessment, "connection_plan": connection_plan},
            ),
            WorkerTask(
                task_type="use_case_recommendation",
                summary="Infer the best attainable use case from the device evidence and user goals.",
                prompt=(
                    "Given the device evidence and user goals, summarize the best attainable device rehabilitation outcome.\n\n"
                    f"Recommendation seed: {json_safe(recommendation)}"
                ),
                risk=TaskRisk.MEDIUM,
                retry_budget=1,
                context={"recommendation": recommendation},
            ),
        ]
        worker_executions = (
            [
                self.worker_runtime.execute(route, task, session_dir)
                for route, task in zip(worker_routes, worker_tasks, strict=False)
            ]
            if execute_workers
            else []
        )

        generated_runtime: dict[str, Any] = {}
        patch_result: dict[str, Any] = {}
        execution_result: dict[str, Any] = {}
        inspection: dict[str, Any] = {}
        if blocker.get("machine_solvable") and execute_workers:
            worker_routes.append(
                self.worker_router.route(
                    WorkerTask(
                        task_type="machine_remediation",
                        summary=str(blocker.get("summary", "Recoverable blocker remediation")),
                        prompt=(
                            "Review this machine-solvable blocker and propose the smallest safe repo-aware fix path.\n\n"
                            f"Blocker: {json_safe(blocker)}"
                        ),
                        risk=TaskRisk.MEDIUM,
                        needs_repo_edit=True,
                        local_retry_count=int(current_state.remediation_iteration),
                        retry_budget=2,
                        context={"blocker": blocker},
                    )
                )
            )
            worker_executions.append(
                self.worker_runtime.execute(
                    worker_routes[-1],
                    WorkerTask(
                        task_type="machine_remediation",
                        summary=str(blocker.get("summary", "Recoverable blocker remediation")),
                        prompt=(
                            "Review this machine-solvable blocker and propose the smallest safe repo-aware fix path.\n\n"
                            f"Blocker: {json_safe(blocker)}"
                        ),
                        risk=TaskRisk.MEDIUM,
                        needs_repo_edit=True,
                        local_retry_count=int(current_state.remediation_iteration),
                        retry_budget=2,
                        context={"blocker": blocker},
                        target_files=["app/core/orchestrator.py", "app/core/runtime_workers.py"],
                    ),
                    session_dir,
                )
            )
            self._safe_transition(session_dir, "REMEDIATION_DECIDE", f"Runtime selected remediation path `{blocker['planned_next_action']}`")
            self._safe_transition(session_dir, "TASK_CREATE", "Creating a remediation task from the current blocker")
            current_state = self.sessions.load_session_state(session_dir)
            current_state.remediation_iteration += 1
            self.sessions.write_session_state(session_dir, current_state)
            self._safe_transition(session_dir, "CODEGEN_WRITE", "Writing executable remediation artifact into the active session")
            generated_runtime = self.codegen_runtime.generate(session_dir, blocker, connection_plan, build_plan)
            self._safe_transition(session_dir, "PATCH_APPLY", "Registering generated remediation artifacts")
            patch_result = self.patch_executor.apply(session_dir, generated_runtime)
            self._safe_transition(session_dir, "EXECUTE_ARTIFACT", "Executing generated remediation artifact")
            execution_result = self.codegen_runtime.execute_generated(session_dir, generated_runtime)
            self._safe_transition(session_dir, "INSPECT_RESULT", "Inspecting remediation artifact result")
            inspection = self.codegen_runtime.inspect_result(execution_result)
            self._apply_inspection_updates(session_dir, inspection, assessment, engagement)
            current_profile = self.sessions.load_device_profile(session_dir)
            current_state = self.sessions.load_session_state(session_dir)
            assessment = {**assessment, **inspection.get("assessment_updates", {})}
            engagement = {**engagement, **inspection.get("engagement_updates", {})}
            knowledge_match = self.knowledge_lookup.lookup(current_profile.manufacturer, current_profile.model)
            connection_plan = self.connection_engine.build_plan(current_profile, current_state, assessment, engagement)
            blocker = self.blockers.classify(
                current_profile,
                current_state,
                assessment,
                engagement,
                connection_plan,
                remediation_result=inspection,
            )
            current_state.current_blocker_type = blocker["blocker_type"]
            current_state.blocker_confidence = blocker["confidence"]
            self.sessions.write_session_state(session_dir, current_state)
            if blocker["blocker_type"] != "none":
                self._safe_transition(session_dir, "BLOCKER_CLASSIFY", "Reclassifying blocker after remediation artifact execution")
        else:
            self._safe_transition(session_dir, "QUESTION_GATE", "Blocker requires minimal external action or approval")

        retry_plan = self.retry_planner.build_plan(blocker, generated_runtime or None)
        if flash_plan.requires_wipe and execute_workers:
            worker_routes.append(
                self.worker_router.route(
                    WorkerTask(
                        task_type="install_planning",
                        summary="Review destructive install planning and safety gates.",
                        risk=TaskRisk.HIGH,
                        architecture_level=True,
                    )
                )
            )
            worker_executions.append(
                self.worker_runtime.execute(
                    worker_routes[-1],
                    WorkerTask(
                        task_type="install_planning",
                        summary="Review destructive install planning and safety gates.",
                        prompt=(
                            "Review this install plan and explain whether ForgeOS should escalate rather than continue locally.\n\n"
                            f"Flash plan: {json_safe(to_dict(flash_plan))}"
                        ),
                        risk=TaskRisk.HIGH,
                        architecture_level=True,
                        retry_budget=1,
                        context={"flash_plan": to_dict(flash_plan)},
                    ),
                    session_dir,
                )
            )

        approval = self.sessions.load_destructive_approval(session_dir)
        install_gate = self.policy_guard.evaluate_install_gate(
            policy=self.policy,
            flash_plan=flash_plan,
            approval=approval,
            backup_plan=backup_plan["plan"],
        )
        runtime_gate = self.policy_guard.evaluate_research_gate(blocker)
        self._safe_transition(session_dir, "BACKUP_READY", "Backup and restore readiness recorded for this session")
        transport_value = (
            current_profile.transport.value
            if hasattr(current_profile.transport, "value")
            else str(current_profile.transport)
        )
        manageable_transport = transport_value in MANAGEABLE_TRANSPORTS
        install_candidate = (
            assessment.get("support_status") == "actionable"
            and build_plan.get("os_path") != "research_only_path"
            and flash_plan.status != "deferred"
            and manageable_transport
        )
        preview_ready = install_candidate
        verification_ready = install_candidate and backup_plan["plan"].get("restore_path_feasible", False)

        if preview_ready and execute_runtime_pipelines:
            self._safe_transition(session_dir, "PREVIEW_BUILD", "ForgeOS is generating a preview for the proposed path")
            preview_execution = self.preview_pipeline.execute(
                session_dir=session_dir,
                build_plan=build_plan,
                recommendation=recommendation,
                assessment=assessment,
                connection_plan=connection_plan,
            )
            self._safe_transition(session_dir, "PREVIEW_REVIEW", "Preview output is ready for review")
        else:
            preview_execution = self.preview_pipeline.defer(
                session_dir=session_dir,
                reason=(
                    "Preview is deferred until ForgeOS has a manageable transport, an actionable assessment, "
                    "and a non-research replacement path."
                ),
                build_plan=build_plan,
                recommendation=recommendation,
                assessment=assessment,
                connection_plan=connection_plan,
            )

        if verification_ready and execute_runtime_pipelines:
            self._safe_transition(session_dir, "INTERACTIVE_VERIFY", "ForgeOS is running verification before any install decision")
            verification_execution = self.verification_pipeline.execute(
                session_dir=session_dir,
                assessment=assessment,
                backup_plan=backup_plan["plan"],
                restore_plan=restore_plan,
                flash_plan=to_dict(flash_plan),
            )
        else:
            verification_execution = self.verification_pipeline.defer(
                session_dir=session_dir,
                reason=(
                    "Verification is deferred until preview and backup readiness are complete and ForgeOS has a viable install candidate."
                    if execute_runtime_pipelines
                    else "Verification is deferred in lightweight GUI mode until explicit runtime execution is requested."
                ),
            )

        install_ready = (
            flash_plan.status != "deferred"
            and preview_execution.status == "executed"
            and verification_execution.status == "executed"
            and manageable_transport
        )
        if install_ready:
            self._safe_transition(session_dir, "INSTALL_APPROVAL", "The session is ready for operator install review")
        runtime_files = self.runtime_planner.materialize(
            session_dir=session_dir,
            state=self.sessions.load_session_state(session_dir),
            assessment=assessment,
            connection_plan=connection_plan,
            build_plan=build_plan,
            backup_plan=backup_plan["plan"],
            restore_plan=restore_plan,
            blocker=blocker,
            worker_routes=worker_routes,
            worker_executions=worker_executions,
            install_gate=install_gate,
            runtime_gate=runtime_gate,
            recommendation=recommendation,
            preview_execution=preview_execution,
            verification_execution=verification_execution,
        )
        if blocker["blocker_type"] == "none":
            self._safe_transition(session_dir, "CONNECTIVITY_VALIDATE", "Runtime resolved immediate blocker and can continue validation")
        elif not blocker.get("machine_solvable"):
            self._safe_transition(session_dir, "QUESTION_GATE", "Runtime hit a true external-action or approval boundary")
        return {
            "profile": current_profile,
            "state": self.sessions.load_session_state(session_dir),
            "assessment": assessment,
            "engagement": engagement,
            "knowledge_match": knowledge_match,
            "connection_plan": connection_plan,
            "blocker": blocker,
            "build_plan": build_plan,
            "backup_plan": backup_plan,
            "restore_plan": restore_plan,
            "flash_plan": flash_plan,
            "generated_runtime": generated_runtime,
            "patch_result": patch_result,
            "execution_result": execution_result,
            "inspection": inspection,
            "retry_plan": retry_plan,
            "recommendation": recommendation,
            "worker_routes": worker_routes,
            "worker_executions": worker_executions,
            "install_gate": install_gate,
            "runtime_gate": runtime_gate,
            "preview_execution": preview_execution,
            "verification_execution": verification_execution,
            "runtime_files": runtime_files,
        }

    def _read_operator_review(self, session_dir: Path) -> dict[str, Any]:
        path = session_dir / "runtime" / "operator-review.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            self.logger.exception("Failed to read operator review from %s", path)
            return {}

    def _apply_inspection_updates(
        self,
        session_dir: Path,
        inspection: dict[str, Any],
        assessment: dict[str, Any],
        engagement: dict[str, Any],
    ) -> None:
        profile_updates = inspection.get("profile_updates", {})
        if profile_updates:
            profile = self.sessions.load_device_profile(session_dir)
            for key, value in profile_updates.items():
                if hasattr(profile, key) and value not in {None, ""}:
                    if key == "transport":
                        profile.transport = profile.transport.__class__(value)
                    else:
                        setattr(profile, key, value)
            self.sessions.write_device_profile(session_dir, profile)
            self.sessions.annotate(session_dir, inspection.get("summary", "Remediation artifact updated the device profile."))
        if inspection.get("engagement_updates"):
            engagement.update(inspection["engagement_updates"])
        if inspection.get("assessment_updates"):
            assessment.update(inspection["assessment_updates"])

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
        backup_plan_path = session_dir / "backup" / "backup-plan.json"
        if not backup_plan_path.exists():
            return {
                "status": "blocked_no_backup_bundle",
                "summary": "Destructive execution is blocked because no pre-wipe backup bundle exists for this session.",
                "details": {
                    "dry_run": True,
                    "can_execute": False,
                    "reason": "backup_bundle_missing",
                },
            }
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

    def _load_report_details(self, session_dir: Path, report_name: str) -> dict[str, Any]:
        path = session_dir / "reports" / f"{report_name}.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            return {}
        return payload.get("details", {})


def json_safe(payload: Any) -> str:
    try:
        return str(to_dict(payload) if not isinstance(payload, (str, int, float, bool)) else payload)
    except Exception:
        return str(payload)

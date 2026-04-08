import json
from pathlib import Path

from app.core.models import (
    ApprovalGate,
    DestructiveApproval,
    FlashPlan,
    PreviewExecution,
    PolicyModel,
    SessionState,
    SessionStateName,
    SupportStatus,
    TaskRisk,
    Transport,
    WorkerExecution,
    WorkerRouteDecision,
    VerificationExecution,
    WorkerRole,
    WorkerTier,
)
from app.core.orchestrator import ForgeOrchestrator
from app.core.policy_guard import PolicyGuard
from app.core.runtime_pipelines import PreviewPipeline, VerificationPipeline
from app.core.runtime_planner import RuntimePlanner
from app.core.runtime_workers import WorkerRegistry, WorkerRouter, WorkerRuntime, WorkerTask
from app.core.session_manager import SessionManager


def test_worker_router_prefers_local_editor_for_repo_edits(tmp_path: Path) -> None:
    registry = WorkerRegistry(tmp_path).discover()
    router = WorkerRouter(registry)
    decision = router.route(
        WorkerTask(
            task_type="machine_remediation",
            summary="Patch a generated session helper",
            needs_repo_edit=True,
            risk=TaskRisk.MEDIUM,
        )
    )
    if registry.get(WorkerRole.LOCAL_EDITOR).available:
        assert decision.selected_worker == WorkerRole.LOCAL_EDITOR
        assert decision.adapter_name == "aider_local_editor"
    else:
        assert decision.selected_worker == WorkerRole.FRONTIER_ARCHITECT
    assert isinstance(registry.inventory(), list)


def test_worker_router_escalates_high_risk_work(tmp_path: Path) -> None:
    router = WorkerRouter(WorkerRegistry(tmp_path).discover())
    decision = router.route(
        WorkerTask(
            task_type="install_planning",
            summary="Review destructive install planning",
            architecture_level=True,
            risk=TaskRisk.HIGH,
        )
    )
    assert decision.selected_worker == WorkerRole.FRONTIER_ARCHITECT


def test_policy_guard_blocks_install_without_restore_confirmation(tmp_path: Path) -> None:
    guard = PolicyGuard(tmp_path)
    gate = guard.evaluate_install_gate(
        policy=PolicyModel(),
        flash_plan=FlashPlan(
            session_id="test",
            build_path="aftermarket_path",
            restore_path_available=True,
            summary="Flash ready",
        ),
        approval=DestructiveApproval(session_id="test", approved=True, confirmation_phrase="WIPE_AND_REBUILD"),
        backup_plan={"backup_bundle_path": "/tmp/bundle.tar.gz"},
    )
    assert not gate.allowed
    assert "Operator has not confirmed the restore path." in gate.missing_requirements


def test_policy_guard_blocks_self_improvement_when_budget_or_scope_is_exceeded(tmp_path: Path) -> None:
    guard = PolicyGuard(tmp_path)
    gate = guard.evaluate_self_improvement_gate(
        policy=PolicyModel(max_api_tokens_per_session=10, max_experiment_loop_iterations=1),
        session_dir=tmp_path / "devices" / "demo",
        estimated_tokens_used=12,
        iteration_count=1,
        proposed_paths=[tmp_path / "master" / "unsafe.py"],
    )

    assert gate.allowed is False
    assert any("outside policy scope" in item for item in gate.missing_requirements)
    assert any("token budget" in item for item in gate.missing_requirements)
    assert any("iteration budget" in item for item in gate.missing_requirements)


def test_worker_runtime_executes_with_transcript(tmp_path: Path) -> None:
    registry = WorkerRegistry(tmp_path).discover()
    router = WorkerRouter(registry)
    runtime = WorkerRuntime(tmp_path, registry)
    session_dir = tmp_path / "devices" / "demo"
    (session_dir / "runtime").mkdir(parents=True)
    task = WorkerTask(
        task_type="device_discovery",
        summary="Summarize device discovery",
        prompt="hello",
        repetitive=True,
        invocation_override=["/bin/sh", "-lc", "printf '{\"result\":\"ok\"}'"],
    )
    route = router.route(task)
    execution = runtime.execute(route, task, session_dir)
    assert execution.status == "completed"
    assert execution.confidence > 0.5
    assert Path(execution.transcript_path).exists()


def test_runtime_pipelines_write_execution_outputs(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "demo"
    session_dir.mkdir(parents=True)
    preview = PreviewPipeline(tmp_path).execute(
        session_dir=session_dir,
        build_plan={
            "os_path": "maintainable_hardened_path",
            "proposed_os_name": "Hardened stock Android for Lightweight Custom Android",
            "included_feature_labels": ["Debloated app set", "Visible restore and recovery entry point"],
            "rejected_feature_labels": ["Automatic wipe/install start"],
        },
        recommendation={"recommended_use_case": "lightweight_custom_android"},
        assessment={"support_status": "actionable"},
        connection_plan={"recommended_adapter": {"adapter_id": "adb"}},
    )
    verification = VerificationPipeline(tmp_path).execute(
        session_dir=session_dir,
        assessment={"support_status": "actionable", "summary": "ready"},
        backup_plan={"backup_bundle_path": "/tmp/bundle.tar.gz"},
        restore_plan={"details": {"steps": ["restore"]}},
        flash_plan={"build_path": "maintainable_hardened_path"},
    )
    assert preview.status == "executed"
    assert verification.status == "executed"
    assert any(path.endswith("preview-execution.json") for path in preview.generated_files)
    assert any(path.endswith("proposed-os-preview.tar.gz") for path in preview.generated_files)
    assert any(path.endswith("experience-preview.md") for path in preview.generated_files)
    assert any(path.endswith("next-steps.md") for path in preview.generated_files)
    assert any(path.endswith("verification-execution.json") for path in verification.generated_files)


def test_runtime_planner_writes_runtime_artifacts(tmp_path: Path) -> None:
    (tmp_path / "master" / "strategies").mkdir(parents=True)
    manager = SessionManager(tmp_path)
    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Samsung",
            "model": "Galaxy Test",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )
    planner = RuntimePlanner(tmp_path, manager)
    state = SessionState(session_id=session_dir.name, state=SessionStateName.RECOMMEND)
    files = planner.materialize(
        session_dir=session_dir,
        state=state,
        assessment={"summary": "Assessment summary", "support_status": "actionable"},
        connection_plan={"recommended_adapter": {"adapter_id": "adb"}},
        build_plan={"os_path": "maintainable_hardened_path"},
        backup_plan={"restore_path_feasible": True},
        restore_plan={"details": {"steps": ["Restore from the saved bundle."]}},
        blocker={"blocker_type": "none", "machine_solvable": True},
        worker_routes=[],
        worker_executions=[],
        install_gate=ApprovalGate(
            action="wipe_and_install",
            allowed=False,
            requires_explicit_approval=True,
            reason="Approval missing",
        ),
        runtime_gate=ApprovalGate(
            action="autonomous_runtime_progress",
            allowed=True,
            requires_explicit_approval=False,
            reason="Continue",
        ),
        recommendation={
            "recommended_use_case": "lightweight_custom_android",
            "options": [
                {
                    "option_id": "lightweight_custom_android",
                    "label": "Lightweight custom Android",
                    "fit_score": 0.8,
                    "rationale": "Best fit",
                }
            ],
        },
        preview_execution=PreviewExecution(
            status="executed",
            summary="Preview done",
            mode="simulated",
        ),
        verification_execution=VerificationExecution(
            status="executed",
            summary="Verification done",
        ),
    )
    assert Path(files["runtime_plan_path"]).exists()
    assert Path(files["proposal_manifest_path"]).exists()
    assert Path(files["worker_routing_path"]).exists()
    assert Path(files["audit_log_path"]).exists()
    assert files["experiment_log_path"].endswith("reports/autonomous-experiments.json")
    manifest = Path(files["proposal_manifest_path"]).read_text()
    assert "included_features" in manifest
    assert "proposed_os_name" in manifest


def test_runtime_planner_proposal_manifest_keeps_recommended_summary_when_selection_differs(tmp_path: Path) -> None:
    from app.core.models import PreviewExecution
    from app.core.runtime_planner import RuntimePlanner
    from app.core.session_manager import SessionManager

    sessions = SessionManager(tmp_path)
    session_dir = sessions.create_or_resume(
        {
            "manufacturer": "Samsung",
            "model": "SM-A520W",
            "serial": "ABC123",
        }
    )
    (session_dir / "runtime").mkdir(parents=True, exist_ok=True)
    (session_dir / "runtime" / "operator-review.json").write_text(
        json.dumps(
            {
                "selected_option_id": "home_control_panel",
                "accepted_feature_ids": [],
                "rejected_feature_ids": [],
            },
            indent=2,
        )
    )
    planner = RuntimePlanner(tmp_path, sessions)

    manifest = planner._proposal_manifest(
        session_dir=session_dir,
        build_plan={"os_path": "hardened_stock_path"},
        recommendation={
            "recommended_use_case": "accessibility_focused_phone",
            "options": [
                {"option_id": "accessibility_focused_phone", "label": "Accessibility-focused phone", "fit_score": 0.82},
                {"option_id": "home_control_panel", "label": "Home control panel", "fit_score": 0.58},
            ],
        },
        preview_execution=PreviewExecution(status="deferred", summary="Deferred", mode="deferred"),
    )

    assert manifest["recommended_use_case"] == "accessibility_focused_phone"
    assert manifest["selected_option_id"] == "home_control_panel"
    assert manifest["proposed_os_name"] == "Hardened stock Android for Accessibility Focused Phone"
    assert "accessibility focused phone" in manifest["proposal_summary"]


def test_orchestrator_runs_bounded_worker_self_heal_loop(tmp_path: Path) -> None:
    (tmp_path / "master" / "policies").mkdir(parents=True)
    (tmp_path / "master" / "policies" / "default_policy.json").write_text(
        """{
  "policy_version": "1.0",
  "default_dry_run": true,
  "require_restore_path": true,
  "allow_live_destructive_actions": false,
  "require_explicit_wipe_phrase": true,
  "allow_bootloader_relock": false,
  "open_vscode_on_launch": false,
  "open_vscode_on_session_create": false,
  "enable_codex_handoff": false,
  "priority_order": ["restore_path"],
  "host_requirements": {"platforms": ["linux"], "preferred_desktop": "Pop!_OS", "tools": ["adb", "fastboot"]}
}"""
    )
    orchestrator = ForgeOrchestrator(tmp_path)
    session_dir = tmp_path / "devices" / "demo"
    session_dir.mkdir(parents=True)

    route = WorkerRouteDecision(
        task_type="device_discovery",
        selected_worker=WorkerRole.LOCAL_GENERAL,
        selected_tier=WorkerTier.LOCAL,
        rationale="test route",
        adapter_name="goose_local_worker",
    )
    task = WorkerTask(
        task_type="device_discovery",
        summary="Discover device",
        prompt="discover",
        retry_budget=1,
    )
    failed = WorkerExecution(
        worker=WorkerRole.LOCAL_GENERAL.value,
        adapter_name="goose_local_worker",
        task_type="device_discovery",
        status="failed",
        summary="device_discovery failed",
        stderr="boom",
        confidence=0.1,
    )
    calls: list[str] = []

    def fake_execute(route_arg, task_arg, session_dir_arg):
        calls.append(task_arg.task_type)
        status = "completed"
        summary = f"{task_arg.task_type} recovered"
        if task_arg.task_type == "worker_self_heal":
            summary = "self heal applied"
        return WorkerExecution(
            worker=route_arg.selected_worker.value,
            adapter_name=route_arg.adapter_name,
            task_type=task_arg.task_type,
            status=status,
            summary=summary,
            transcript_path=str(session_dir_arg / "runtime" / f"{task_arg.task_type}.json"),
            confidence=0.8,
        )

    orchestrator.worker_runtime.execute = fake_execute  # type: ignore[method-assign]

    extra_routes, extra_execs, loop_report = orchestrator._run_local_worker_fix_loop(
        session_dir=session_dir,
        worker_routes=[route],
        worker_tasks=[task],
        worker_executions=[failed],
    )

    assert calls == ["worker_self_heal", "device_discovery"]
    assert len(extra_routes) == 2
    assert len(extra_execs) == 2
    assert loop_report["status"] == "recovered"
    assert loop_report["recovered_tasks"] == 1


def test_recompute_runtime_persists_experiment_and_source_plan(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "master" / "policies").mkdir(parents=True)
    (tmp_path / "master" / "policies" / "default_policy.json").write_text(
        json.dumps(
            {
                "policy_version": "1.0",
                "default_dry_run": True,
                "require_restore_path": True,
                "allow_live_destructive_actions": False,
                "require_explicit_wipe_phrase": True,
                "allow_bootloader_relock": False,
                "open_vscode_on_launch": False,
                "open_vscode_on_session_create": False,
                "enable_codex_handoff": False,
                "priority_order": ["restore_path"],
                "host_requirements": {"platforms": ["linux"], "preferred_desktop": "Pop!_OS", "tools": ["adb", "fastboot"]},
            }
        )
    )
    orchestrator = ForgeOrchestrator(tmp_path)
    session_dir = orchestrator.sessions.create_or_resume(
        {
            "manufacturer": "Samsung",
            "model": "SM-A520W",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )
    state = orchestrator.sessions.load_session_state(session_dir)
    state.support_status = SupportStatus.ACTIONABLE
    state.selected_strategy = "hardened_existing_os"
    orchestrator.sessions.write_session_state(session_dir, state)

    monkeypatch.setattr(orchestrator.knowledge_lookup, "lookup", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(orchestrator.connection_engine, "build_plan", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(orchestrator.adapter_registry, "has_master_adapter", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(orchestrator.research_worker, "research_firmware", lambda **_kwargs: None)
    monkeypatch.setattr(orchestrator.research_worker, "research_blocker", lambda **_kwargs: None)
    monkeypatch.setattr(
        orchestrator.backup_restore,
        "execute",
        lambda *_args, **_kwargs: {
            "plan": {
                "restore_path_feasible": True,
                "summary": "Backup ready",
                "backup_bundle_path": "/tmp/bundle.tar.gz",
            }
        },
    )
    monkeypatch.setattr(
        orchestrator.restore_controller,
        "execute",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "summary": "Restore ready",
            "details": {"steps": ["Restore"]},
            "restore_plan_path": str(session_dir / "restore" / "restore-plan.json"),
        },
    )
    monkeypatch.setattr(
        orchestrator.use_case_recommender,
        "execute",
        lambda *_args, **_kwargs: {"recommended_use_case": "lightweight_custom_android", "options": []},
    )
    monkeypatch.setattr(
        orchestrator.build_resolver,
        "execute",
        lambda *_args, **_kwargs: {"os_path": "research_only_path", "reason": "Need source artifacts."},
    )
    monkeypatch.setattr(
        orchestrator.image_builder,
        "execute",
        lambda *_args, **_kwargs: {
            "status": "missing",
            "details": {"install_mode": "unavailable", "missing_requirements": []},
            "artifacts": [],
        },
    )
    monkeypatch.setattr(
        orchestrator.flash_executor,
        "build_plan",
        lambda **_kwargs: FlashPlan(
            session_id=session_dir.name,
            build_path="research_only_path",
            requires_wipe=False,
            restore_path_available=True,
            status="deferred",
            summary="Waiting on source artifacts.",
        ),
    )
    blocker_calls = {"count": 0}

    def fake_classify(*_args, **_kwargs):
        blocker_calls["count"] += 1
        if blocker_calls["count"] == 1:
            return {
                "blocker_type": "source_blocker",
                "machine_solvable": True,
                "confidence": 0.9,
                "planned_next_action": "source_acquisition_and_staging",
                "summary": "Need firmware package.",
                "retry_budget": 2,
            }
        return {
            "blocker_type": "none",
            "machine_solvable": False,
            "confidence": 1.0,
            "planned_next_action": "",
            "summary": "Resolved",
            "retry_budget": 0,
        }

    monkeypatch.setattr(orchestrator.blockers, "classify", fake_classify)
    monkeypatch.setattr(orchestrator, "_run_local_worker_fix_loop", lambda **_kwargs: ([], [], {"status": "not_needed", "summary": "No-op"}))
    monkeypatch.setattr(
        orchestrator.worker_runtime,
        "execute",
        lambda route, task, session_dir_arg: WorkerExecution(
            worker=route.selected_worker.value,
            adapter_name=route.adapter_name,
            task_type=task.task_type,
            status="completed",
            summary=f"{task.task_type} completed",
            transcript_path=str(session_dir_arg / "runtime" / f"{task.task_type}.json"),
            confidence=0.9,
        ),
    )

    def fake_execute_generated(session_dir_arg: Path, _generated: dict[str, object], **_kwargs) -> dict[str, object]:
        plan_path = session_dir_arg / "plans" / "source-acquisition-plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps(
                {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "staged_files": [str(session_dir_arg / "artifacts" / "os-source" / "update.zip")],
                }
            )
        )
        return {"status": "executed", "summary": "Executed", "result": {}, "elapsed_seconds": 0.1}

    monkeypatch.setattr(orchestrator.codegen_runtime, "execute_generated", fake_execute_generated)
    monkeypatch.setattr(
        orchestrator.codegen_runtime,
        "inspect_result",
        lambda *_args, **_kwargs: {
            "status": "solved",
            "summary": "Staged firmware.",
            "profile_updates": {},
            "engagement_updates": {},
            "assessment_updates": {"support_status": "actionable"},
            "evidence": {
                "source_acquisition": {"staged_files": [str(session_dir / "artifacts" / "os-source" / "update.zip")]},
                "remote_source_resolution": {"status": "ok"},
            },
            "next_action": "reclassify",
        },
    )
    monkeypatch.setattr(
        orchestrator.policy_guard,
        "evaluate_install_gate",
        lambda **_kwargs: ApprovalGate(action="hold", allowed=False, requires_explicit_approval=True, reason="not ready"),
    )
    monkeypatch.setattr(
        orchestrator.policy_guard,
        "evaluate_research_gate",
        lambda *_args, **_kwargs: ApprovalGate(action="continue", allowed=True, requires_explicit_approval=False, reason="clear"),
    )

    result = orchestrator.recompute_session_runtime(session_dir)

    experiments_path = session_dir / "reports" / "autonomous-experiments.json"
    source_plan_path = session_dir / "plans" / "source-acquisition-plan.json"
    runtime_audit_path = session_dir / "runtime" / "runtime-audit.json"

    assert source_plan_path.exists()
    assert experiments_path.exists()
    assert runtime_audit_path.exists()

    experiments = json.loads(experiments_path.read_text())
    runtime_audit = json.loads(runtime_audit_path.read_text())
    assert experiments["fitness"]["fitness_score"] == 1.0
    assert experiments["experiments"][-1]["decision"] == "advance"
    assert experiments["experiments"][-1]["blocker_id"].startswith("source_blocker:")
    assert experiments["experiments"][-1]["elapsed_seconds"] >= 0.0
    assert runtime_audit["governance_summary"]["estimated_tokens_used"] > 0
    assert runtime_audit["self_improvement_summary"]["selected_proposal"]["proposal_id"]
    assert result["runtime_files"]["audit_log_path"].endswith("runtime/runtime-audit.json")

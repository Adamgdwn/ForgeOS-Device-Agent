from pathlib import Path

from app.core.models import (
    ApprovalGate,
    DestructiveApproval,
    FlashPlan,
    PreviewExecution,
    PolicyModel,
    SessionState,
    SessionStateName,
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
    manifest = Path(files["proposal_manifest_path"]).read_text()
    assert "included_features" in manifest
    assert "proposed_os_name" in manifest


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

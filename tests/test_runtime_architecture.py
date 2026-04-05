from pathlib import Path

from app.core.models import (
    ApprovalGate,
    DestructiveApproval,
    FlashPlan,
    PolicyModel,
    SessionState,
    SessionStateName,
    TaskRisk,
    Transport,
    WorkerRole,
)
from app.core.policy_guard import PolicyGuard
from app.core.runtime_planner import RuntimePlanner
from app.core.runtime_workers import WorkerRegistry, WorkerRouter, WorkerTask
from app.core.session_manager import SessionManager


def test_worker_router_prefers_local_editor_for_repo_edits(tmp_path: Path) -> None:
    router = WorkerRouter(WorkerRegistry(tmp_path).discover())
    decision = router.route(
        WorkerTask(
            task_type="machine_remediation",
            summary="Patch a generated session helper",
            needs_repo_edit=True,
            risk=TaskRisk.MEDIUM,
        )
    )
    assert decision.selected_worker == WorkerRole.LOCAL_EDITOR


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
    )
    assert Path(files["runtime_plan_path"]).exists()
    assert Path(files["worker_routing_path"]).exists()
    assert Path(files["audit_log_path"]).exists()

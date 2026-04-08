from __future__ import annotations

import json
from pathlib import Path

from app.core.models import (
    ApprovalGate,
    FlashPlan,
    PreviewExecution,
    SessionStateName,
    SupportStatus,
    Transport,
    VerificationExecution,
)
from app.core.orchestrator import ForgeOrchestrator
from app.core.promotion import PromotionEngine
from app.core.session_manager import SessionManager
from app.core.state_machine import ALLOWED_TRANSITIONS


def test_iterate_allows_deep_scan_transition() -> None:
    assert SessionStateName.DEEP_SCAN in ALLOWED_TRANSITIONS[SessionStateName.ITERATE]


def test_session_manager_finds_waiting_session(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Samsung",
            "model": "SM-A520W",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )
    state = manager.load_session_state(session_dir)
    state.state = SessionStateName.QUESTION_GATE
    manager.write_session_state(session_dir, state)

    assert manager.find_waiting_session("ABC123") == session_dir


def test_session_manager_persists_iterate_count(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Samsung",
            "model": "SM-A520W",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )
    state = manager.load_session_state(session_dir)
    state.iterate_count = 2
    manager.write_session_state(session_dir, state)

    reloaded = manager.load_session_state(session_dir)

    assert reloaded.iterate_count == 2


def test_orchestrator_resumes_waiting_session(monkeypatch, tmp_path: Path) -> None:
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
    manager = orchestrator.sessions
    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Samsung",
            "model": "SM-A520W",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )
    state = manager.load_session_state(session_dir)
    state.state = SessionStateName.QUESTION_GATE
    state.support_status = SupportStatus.ACTIONABLE
    manager.write_session_state(session_dir, state)

    monkeypatch.setattr(
        orchestrator.device_probe,
        "execute",
        lambda payload: {
            "device": {
                "manufacturer": "Samsung",
                "model": "SM-A520W",
                "serial": "ABC123",
                "transport": Transport.USB_FASTBOOT,
            }
        },
    )
    calls: list[Path] = []
    monkeypatch.setattr(orchestrator, "recompute_session_runtime", lambda path, lightweight=False: calls.append(path) or {})

    returned = orchestrator.handle_device_event({"serial": "ABC123", "transport": Transport.USB_FASTBOOT})

    assert returned == session_dir
    assert calls == [session_dir]


def test_runtime_materializes_resumed_question_gate_as_iterate(monkeypatch, tmp_path: Path) -> None:
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
    state.state = SessionStateName.QUESTION_GATE
    state.support_status = SupportStatus.ACTIONABLE
    state.selected_strategy = "hardened_stock"
    orchestrator.sessions.write_session_state(session_dir, state)

    monkeypatch.setattr(orchestrator.knowledge_lookup, "lookup", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(orchestrator.connection_engine, "build_plan", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(orchestrator.adapter_registry, "has_master_adapter", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(orchestrator.backup_restore, "execute", lambda *_args, **_kwargs: {"plan": {"restore_path_feasible": False}})
    monkeypatch.setattr(orchestrator.restore_controller, "execute", lambda *_args, **_kwargs: {"status": "ready"})
    monkeypatch.setattr(
        orchestrator.use_case_recommender,
        "execute",
        lambda *_args, **_kwargs: {"recommended_use_case": "research_hold", "options": []},
    )
    monkeypatch.setattr(
        orchestrator.build_resolver,
        "execute",
        lambda *_args, **_kwargs: {"os_path": "research_only_path", "reason": "Waiting on more evidence."},
    )
    monkeypatch.setattr(
        orchestrator.image_builder,
        "execute",
        lambda *_args, **_kwargs: {"status": "missing", "details": {"install_mode": "unavailable", "missing_requirements": []}, "artifacts": []},
    )
    monkeypatch.setattr(
        orchestrator.flash_executor,
        "build_plan",
        lambda **_kwargs: FlashPlan(session_id=session_dir.name, build_path="research_only_path", requires_wipe=False, status="deferred", summary="Waiting"),
    )
    monkeypatch.setattr(
        orchestrator.blockers,
        "classify",
        lambda *_args, **_kwargs: {"blocker_type": "none", "machine_solvable": False, "confidence": 1.0},
    )
    monkeypatch.setattr(orchestrator.retry_planner, "build_plan", lambda *_args, **_kwargs: {"action": "continue"})
    monkeypatch.setattr(orchestrator.retry_planner, "mark_advanced", lambda *_args, **_kwargs: None)
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
    monkeypatch.setattr(
        orchestrator.preview_pipeline,
        "defer",
        lambda **_kwargs: PreviewExecution(status="deferred", summary="Preview deferred.", mode="lightweight"),
    )
    monkeypatch.setattr(
        orchestrator.verification_pipeline,
        "defer",
        lambda **_kwargs: VerificationExecution(status="deferred", summary="Verification deferred."),
    )
    monkeypatch.setattr(orchestrator.worker_router, "route", lambda *_args, **_kwargs: {"worker": "noop"})

    materialized_states: list[str] = []

    def _materialize(**kwargs):
        materialized_states.append(kwargs["state"].state.value)
        return {}

    monkeypatch.setattr(orchestrator.runtime_planner, "materialize", _materialize)

    result = orchestrator._run_runtime_cycle(
        session_dir=session_dir,
        device_payload={"serial": "ABC123", "transport": Transport.USB_ADB},
        assessment={"support_status": "actionable", "summary": "Actionable"},
        engagement={"engagement_status": "ready", "summary": "Ready"},
        user_profile=orchestrator.sessions.load_user_profile(session_dir),
        os_goals=orchestrator.sessions.load_os_goals(session_dir),
        execute_workers=False,
        execute_runtime_pipelines=False,
    )

    assert materialized_states == [SessionStateName.ITERATE.value]
    assert result["state"].state == SessionStateName.ITERATE


def test_promotion_engine_deprecates_adapter_and_audits_probe_no_device(tmp_path: Path) -> None:
    engine = PromotionEngine(tmp_path)
    adapter_path = tmp_path / "master" / "integrations" / "oem_adapters" / "google_pixel_6.py"
    playbook_path = tmp_path / "master" / "playbooks" / "connection" / "google_pixel_6.json"
    adapter_path.parent.mkdir(parents=True, exist_ok=True)
    playbook_path.parent.mkdir(parents=True, exist_ok=True)
    adapter_path.write_text("# adapter")
    playbook_path.write_text("{}")
    (tmp_path / "knowledge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge" / "support_matrix.json").write_text(
        json.dumps({"families": {"google_pixel_6": {"support_level": "developing"}}})
    )

    engine.deprecate_adapter("google_pixel_6", "obsolete")

    deprecated_dirs = list((tmp_path / "master" / "integrations" / "oem_adapters" / "_deprecated").glob("google_pixel_6_*"))
    assert deprecated_dirs
    assert (deprecated_dirs[0] / "deprecation.json").exists()

    review_dir = tmp_path / "promotion" / "adapters" / "google_pixel_6"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "meta.json").write_text(
        json.dumps(
            {
                "key": "google_pixel_6",
                "status": "promoted",
                "test_source": "probe_no_device",
            }
        )
    )
    (tmp_path / "knowledge" / "session_outcomes.json").write_text(json.dumps({"outcomes": {}}))

    assert engine.audit_promoted_adapters() == ["google_pixel_6"]


def test_orchestrator_does_not_auto_promote_review_adapter_when_policy_disables_it(tmp_path: Path) -> None:
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
    review_dir = tmp_path / "promotion" / "adapters" / "google_pixel_6"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "google_pixel_6.py").write_text("# adapter")
    (review_dir / "google_pixel_6.json").write_text("{}")
    (review_dir / "meta.json").write_text(
        json.dumps(
            {
                "key": "google_pixel_6",
                "manufacturer": "Google",
                "model": "Pixel 6",
                "adapter_path": str(review_dir / "google_pixel_6.py"),
                "playbook_path": str(review_dir / "google_pixel_6.json"),
                "test_result": {"status": "probe_pass"},
                "status": "pending_review",
            }
        )
    )

    orchestrator._auto_promote_tested_adapters()

    assert not (tmp_path / "master" / "integrations" / "oem_adapters" / "google_pixel_6.py").exists()

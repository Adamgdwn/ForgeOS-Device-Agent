from __future__ import annotations

import json
from pathlib import Path

from app.core.models import SessionStateName, SupportStatus, Transport
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

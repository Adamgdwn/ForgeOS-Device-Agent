from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.core.models import SupportStatus, Transport
from app.core.orchestrator import ForgeOrchestrator


def _write_policy(root: Path) -> None:
    policy_dir = root / "master" / "policies"
    policy_dir.mkdir(parents=True)
    (policy_dir / "default_policy.json").write_text(
        json.dumps(
            {
                "policy_version": "1.0",
                "default_dry_run": True,
                "require_restore_path": True,
                "allow_live_destructive_actions": False,
                "require_explicit_wipe_phrase": True,
                "allow_long_source_builds": True,
                "max_source_build_seconds": 10,
                "allow_bootloader_relock": False,
                "open_vscode_on_launch": False,
                "open_vscode_on_session_create": False,
                "enable_codex_handoff": False,
                "priority_order": ["restore_path"],
                "host_requirements": {"platforms": ["linux"], "preferred_desktop": "Pop!_OS", "tools": ["adb", "fastboot"]},
            }
        )
    )


def test_orchestrator_resolves_missing_source_before_blocking(monkeypatch, tmp_path: Path) -> None:
    _write_policy(tmp_path)
    orchestrator = ForgeOrchestrator(tmp_path)
    session_dir = orchestrator.sessions.create_or_resume(
        {
            "manufacturer": "Example",
            "model": "Old Tablet",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
            "device_codename": "oldtab",
        }
    )
    state = orchestrator.sessions.load_session_state(session_dir)
    state.support_status = SupportStatus.ACTIONABLE
    orchestrator.sessions.write_session_state(session_dir, state)
    profile = orchestrator.sessions.load_device_profile(session_dir)
    user_profile = orchestrator.sessions.load_user_profile(session_dir)
    user_profile.lawful_use_attested = True
    orchestrator.sessions.write_user_profile(session_dir, user_profile)
    monkeypatch.setattr(orchestrator.research_worker, "research_firmware", lambda **_kwargs: None)

    def fake_resolver(payload, dry_run=True):
        source_dir = session_dir / "artifacts" / "os-source"
        source_dir.mkdir(parents=True, exist_ok=True)
        update_path = source_dir / "lineage-oldtab.zip"
        with zipfile.ZipFile(update_path, "w") as archive:
            archive.writestr("payload.bin", b"payload")
        return {"status": "ok", "blocks": False, "staged_path": str(update_path), "sources": [str(update_path)]}

    monkeypatch.setattr(orchestrator.source_resolver, "execute", fake_resolver)
    monkeypatch.setattr(
        orchestrator.source_builder,
        "execute",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("builder should not run after resolver succeeds")),
    )

    artifacts, acquisition = orchestrator._resolve_missing_source_artifacts(
        session_dir=session_dir,
        current_profile=profile,
        build_plan={"os_path": "maintainable_hardened_path", "proposed_os_name": "LineageOS"},
        initial_artifacts={"status": "missing_source", "details": {"missing_requirements": ["source"]}},
        user_profile=user_profile,
        execute_workers=True,
    )

    assert artifacts["status"] == "ready"
    assert acquisition["status"] == "resolved_from_trusted_source"
    assert artifacts["details"]["install_mode"] == "adb_sideload"

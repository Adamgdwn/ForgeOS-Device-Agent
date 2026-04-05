from pathlib import Path

from app.core.models import SessionStateName, Transport
from app.core.session_manager import SessionManager


def test_create_session_persists_profile_and_state(tmp_path: Path) -> None:
    (tmp_path / "master" / "strategies").mkdir(parents=True)
    manager = SessionManager(tmp_path)

    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Google",
            "model": "Pixel 8",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )

    assert (session_dir / "device-profile.json").exists()
    assert (session_dir / "session-state.json").exists()
    assert (session_dir / "destructive-approval.json").exists()
    assert manager.load_session_state(session_dir).state == SessionStateName.ASSESS


def test_transition_persists_history(tmp_path: Path) -> None:
    (tmp_path / "master" / "strategies").mkdir(parents=True)
    manager = SessionManager(tmp_path)
    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Google",
            "model": "Pixel 8",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )

    manager.transition(session_dir, SessionStateName.PATH_SELECT, "Planning path selected")
    state = manager.load_session_state(session_dir)
    assert state.state == SessionStateName.PATH_SELECT
    assert state.history[-1].to_state == SessionStateName.PATH_SELECT


def test_flash_plan_round_trip(tmp_path: Path) -> None:
    from app.core.models import FlashPlan

    (tmp_path / "master" / "strategies").mkdir(parents=True)
    manager = SessionManager(tmp_path)
    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Google",
            "model": "Pixel 8",
            "serial": "ABC123",
            "transport": Transport.USB_ADB,
        }
    )

    manager.write_flash_plan(
        session_dir,
        FlashPlan(
            session_id=session_dir.name,
            build_path="hardened_stock_path",
            summary="Prepared flash plan",
        ),
    )
    flash_plan = manager.load_flash_plan(session_dir)
    assert flash_plan is not None
    assert flash_plan.build_path == "hardened_stock_path"

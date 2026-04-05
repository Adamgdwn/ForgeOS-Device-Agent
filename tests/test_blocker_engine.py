from pathlib import Path

from app.core.blocker_engine import BlockerEngine
from app.core.models import DeviceProfile, SessionState, SessionStateName, SupportStatus, Transport


def test_blocker_engine_classifies_usb_mtp_as_transport_blocker(tmp_path: Path) -> None:
    engine = BlockerEngine(tmp_path)
    profile = DeviceProfile(
        session_id="sample",
        canonical_name="sample",
        device_codename="sam-1234",
        fingerprint="abc",
        manufacturer="Samsung",
        model="Galaxy A5",
        serial="usb-1",
        transport=Transport.USB_MTP,
    )
    state = SessionState(
        session_id="sample",
        state=SessionStateName.PATH_SELECT,
        support_status=SupportStatus.RESEARCH_ONLY,
    )
    result = engine.classify(
        profile,
        state,
        {"support_status": "research_only", "summary": "USB-only phone"},
        {"engagement_status": "usb_only_detected", "next_steps": ["Enable USB debugging"]},
        {"recommended_adapter": {"adapter_id": "mtp-bridge"}},
    )
    assert result["blocker_type"] == "transport_blocker"
    assert result["machine_solvable"] is False

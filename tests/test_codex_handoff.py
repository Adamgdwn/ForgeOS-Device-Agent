import json
from pathlib import Path

from app.core.codex_handoff import CodexHandoffEngine
from app.core.connection_engine import ConnectionEngine
from app.core.models import (
    DeviceProfile,
    GoogleServicesPreference,
    OSGoals,
    PriorityFocus,
    SessionState,
    SessionStateName,
    SupportStatus,
    TechnicalComfort,
    Transport,
    UserPersona,
    UserProfile,
)


def test_codex_handoff_writes_expected_files(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    session_dir.mkdir(parents=True)

    profile = DeviceProfile(
        session_id="sample",
        canonical_name="sample",
        device_codename="samp-1234",
        fingerprint="abc",
        manufacturer="Samsung",
        model="Galaxy A5",
        serial="SER123",
        transport=Transport.USB_MTP,
    )
    state = SessionState(
        session_id="sample",
        state=SessionStateName.ASSESS,
        support_status=SupportStatus.RESEARCH_ONLY,
        selected_strategy="research_only",
    )
    user_profile = UserProfile(
        session_id="sample",
        persona=UserPersona.SENIOR,
        technical_comfort=TechnicalComfort.LOW,
        primary_priority=PriorityFocus.SIMPLICITY,
        google_services_preference=GoogleServicesPreference.KEEP,
    )
    os_goals = OSGoals(
        session_id="sample",
        top_goal=PriorityFocus.SIMPLICITY,
        secondary_goal=PriorityFocus.SECURITY,
    )
    assessment = {"summary": "USB-only phone detected", "support_status": "research_only"}
    engagement = {"summary": "ForgeOS can see the phone over USB.", "engagement_status": "usb_only_detected"}
    plan = ConnectionEngine(tmp_path).build_plan(profile, state, assessment, engagement)

    result = CodexHandoffEngine(tmp_path).prepare(
        session_dir,
        profile,
        state,
        user_profile,
        os_goals,
        assessment,
        engagement,
        plan,
    )

    assert Path(result["handoff_json"]).exists()
    assert Path(result["task_markdown"]).exists()
    assert Path(result["workspace_file"]).exists()
    payload = json.loads(Path(result["handoff_json"]).read_text())
    assert payload["device"]["model"] == "Galaxy A5"
    assert payload["user_profile"]["persona"] == UserPersona.SENIOR.value


def test_connection_engine_does_not_require_codegen_when_adb_is_connected(tmp_path: Path) -> None:
    profile = DeviceProfile(
        session_id="sample",
        canonical_name="sample",
        device_codename="samp-1234",
        fingerprint="abc",
        manufacturer="Samsung",
        model="Galaxy A5",
        serial="SER123",
        transport=Transport.USB_ADB,
    )
    state = SessionState(
        session_id="sample",
        state=SessionStateName.ASSESS,
        support_status=SupportStatus.RESEARCH_ONLY,
    )
    assessment = {"summary": "ADB is available.", "support_status": "research_only"}
    engagement = {"summary": "ForgeOS can talk to the phone over adb.", "engagement_status": "adb_connected"}

    plan = ConnectionEngine(tmp_path).build_plan(profile, state, assessment, engagement)

    assert plan["recommended_adapter"]["adapter_id"] == "adb"
    assert plan["requires_codex_generation"] is False

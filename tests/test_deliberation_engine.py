from pathlib import Path
from types import SimpleNamespace

from app.core.deliberation import DeliberationEngine


def test_deliberation_blocks_repeat_source_remediation_when_repo_missing(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    transcript_dir = session_dir / "runtime" / "build-from-source"
    transcript_dir.mkdir(parents=True)
    (transcript_dir / "build-transcript.json").write_text(
        '{"status":"failed","stderr":"Android repo tool is required","staged_files":[]}'
    )
    reports_dir = session_dir / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "autonomous-experiments.json").write_text(
        '{"experiments":[{"blocker_before":"source_blocker","advanced":false},{"blocker_before":"source_blocker","advanced":false}]}'
    )

    result = DeliberationEngine(tmp_path).think(
        session_dir=session_dir,
        profile=SimpleNamespace(
            manufacturer="Samsung",
            model="SM-T377W",
            device_codename="gteslte",
            serial="123",
            form_factor=SimpleNamespace(value="tablet"),
            transport=SimpleNamespace(value="usb-adb"),
        ),
        state=SimpleNamespace(
            state=SimpleNamespace(value="BACKUP_READY"),
            selected_strategy="hardened_existing_os",
            remediation_iteration=4,
        ),
        assessment={"support_status": "actionable"},
        engagement={"engagement_status": "adb_connected"},
        connection_plan={},
        build_plan={"os_path": "maintainable_hardened_path"},
        build_artifacts={"status": "missing_source", "details": {"missing_requirements": ["firmware"]}},
        blocker={"blocker_type": "source_blocker", "machine_solvable": True},
        recommendation={"recommended_use_case": "media_device"},
        user_profile=SimpleNamespace(desired_end_product="living room media tablet"),
    )

    policy = result["action_plan"]["execution_policy"]
    assert result["action_plan"]["selected_action"] == "install_host_tool_or_stage_source"
    assert policy["machine_remediation_allowed"] is False
    assert {lesson["id"] for lesson in result["lessons"]} >= {
        "missing_android_repo_tool",
        "repeated_non_advancing_source_attempts",
        "real_artifact_required",
    }
    assert (session_dir / "runtime" / "thinking" / "current-situation.json").exists()
    assert (session_dir / "runtime" / "thinking" / "decision-journal.jsonl").exists()

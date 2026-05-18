from pathlib import Path

from app.core.models import DeviceFormFactor, DeviceProfile, Transport
from app.core.starter_troubleshooting import StarterTroubleshootingLoop


def _profile() -> DeviceProfile:
    return DeviceProfile(
        session_id="sample-session",
        canonical_name="Samsung SM-T377W",
        manufacturer="Samsung",
        model="SM-T377W",
        serial="serial",
        device_codename="gteslte",
        android_version="10",
        fingerprint="samsung/gteslte/gteslte:10/build:user/release-keys",
        transport=Transport.USB_ADB,
        form_factor=DeviceFormFactor.TABLET,
        raw_probe_data={
            "hardware_snapshot": {
                "abi": "armeabi-v7a",
                "boot_slot": "",
                "dynamic_partitions": "",
            }
        },
    )


def _build_plan() -> dict:
    return {
        "source_acquisition": {
            "builder": {
                "status": "blocked",
                "reason": "Android repo tool is missing; skipping repeated local source build attempt until host setup changes.",
            }
        },
        "product_memory": {
            "product_key": "samsung:sm-t377w:gteslte",
            "version_key": "android-10:build-test:fp-test",
            "version": {
                "blockers": {"source_blocker": 4},
                "lessons": [
                    "Local Android source builds need the Android repo tool before retrying.",
                    "No usable flashable artifact has been proven for this version yet.",
                    "This version repeatedly reaches source acquisition; prioritize real firmware or known aftermarket packages.",
                ],
            },
        },
    }


def test_starter_loop_rejects_incompatible_staged_generic_image(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    source_dir = session_dir / "artifacts" / "os-source"
    source_dir.mkdir(parents=True)
    (source_dir / "system-squeak-arm64-ab-vanilla.img.xz").write_bytes(b"x" * (2 * 1024 * 1024))

    result = StarterTroubleshootingLoop(tmp_path).run(
        session_dir=session_dir,
        profile=_profile(),
        build_plan=_build_plan(),
        build_artifacts={"status": "missing_source"},
        blocker={"blocker_type": "source_blocker"},
        deliberation={"action_plan": {"execution_policy": {"machine_remediation_allowed": True}}},
    )

    assert result["status"] == "blocked_incompatible_artifact"
    assert result["model_worker_allowed"] is False
    assert result["machine_worker_allowed"] is False
    assert "arm64" in result["artifact_review"]["rejected_artifacts"][0]["reason"]
    assert any(rule["rule_id"] == "require_android_repo_before_source_build" for rule in result["learned_augmentations"])
    assert (session_dir / "runtime" / "troubleshooting" / "starter-loop.json").exists()
    assert (tmp_path / "knowledge" / "starter_troubleshooting_memory.json").exists()


def test_starter_loop_uses_learned_memory_to_skip_repeated_model_research(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    session_dir.mkdir(parents=True)
    plan = _build_plan()
    plan["source_acquisition"] = {}

    result = StarterTroubleshootingLoop(tmp_path).run(
        session_dir=session_dir,
        profile=_profile(),
        build_plan=plan,
        build_artifacts={"status": "missing_source"},
        blocker={"blocker_type": "source_blocker"},
        deliberation={"action_plan": {"execution_policy": {"machine_remediation_allowed": True}}},
    )

    assert result["status"] == "waiting_for_source_or_host_setup"
    assert result["model_worker_allowed"] is False
    assert any("repo setup" in note for note in result["notes"])

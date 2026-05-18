from pathlib import Path

from app.core.models import DeviceProfile, DeviceFormFactor, SessionState, Transport
from app.core.product_memory import ProductMemoryEngine


def _profile() -> DeviceProfile:
    return DeviceProfile(
        session_id="sample-session",
        canonical_name="Samsung SM-T377W",
        manufacturer="Samsung",
        model="SM-T377W",
        serial="serial",
        device_codename="gteslte",
        android_version="7.1.1",
        fingerprint="samsung/gteslte/gteslte:7.1.1/build123:user/release-keys",
        transport=Transport.USB_ADB,
        form_factor=DeviceFormFactor.TABLET,
        raw_probe_data={"hardware_snapshot": {"build_id": "T377WVLS3BTJ1"}},
    )


def test_product_memory_records_product_and_version(tmp_path: Path) -> None:
    engine = ProductMemoryEngine(tmp_path)
    profile = _profile()

    summary = engine.record_observation(
        session_dir=tmp_path / "devices" / "sample",
        profile=profile,
        state=SessionState(session_id="sample-session", selected_strategy="hardened_existing_os"),
        assessment={"support_status": "actionable", "restore_path_feasible": False},
        build_plan={
            "os_path": "maintainable_hardened_path",
            "source_acquisition": {
                "status": "blocked_by_host_prerequisite",
                "builder": {
                    "status": "blocked",
                    "reason": "Android repo tool is missing; skipping repeated local source build attempt until host setup changes.",
                },
            },
        },
        build_artifacts={"status": "missing_source", "details": {"missing_requirements": ["firmware"]}},
        blocker={"blocker_type": "source_blocker"},
        recommendation={"recommended_use_case": "media_device"},
        restore_plan={"status": "planned", "summary": "metadata backup only"},
    )

    lookup = engine.lookup(profile)

    assert summary["product_key"] == "samsung:sm-t377w:gteslte"
    assert lookup["has_product_memory"] is True
    assert lookup["version"]["android_version"] == "7.1.1"
    assert "source_blocker" in lookup["version"]["blockers"]
    assert any("repo tool" in lesson for lesson in lookup["version"]["lessons"])
    assert (tmp_path / "knowledge" / "product_memory.json").exists()

from pathlib import Path

from app.core.models import DeviceProfile, DeviceFormFactor, SessionState, Transport
from app.core.product_memory import ProductMemoryEngine


def _profile(
    *,
    manufacturer: str | None = "Samsung",
    model: str | None = "SM-T377W",
    codename: str = "gteslte",
    session_id: str = "sample-session",
) -> DeviceProfile:
    return DeviceProfile(
        session_id=session_id,
        canonical_name=f"{manufacturer or 'Unknown'} {model or 'Unknown'}",
        manufacturer=manufacturer,
        model=model,
        serial="serial",
        device_codename=codename,
        android_version="7.1.1",
        fingerprint=f"{manufacturer or 'unknown'}/{codename}/{codename}:7.1.1/build123:user/release-keys",
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


def test_product_memory_merges_weaker_codename_identity_into_precise_product(tmp_path: Path) -> None:
    engine = ProductMemoryEngine(tmp_path)
    coarse_profile = _profile(manufacturer=None, model=None, session_id="coarse-session")
    precise_profile = _profile(session_id="precise-session")

    engine.record_observation(
        session_dir=tmp_path / "devices" / "coarse",
        profile=coarse_profile,
        state=SessionState(session_id="coarse-session", selected_strategy="research_hold"),
        assessment={"support_status": "research_only", "restore_path_feasible": False},
        build_plan={"os_path": "research_only_path", "source_acquisition": {"status": "missing_source"}},
        build_artifacts={"status": "missing_source", "details": {"missing_requirements": ["firmware"]}},
        blocker={"blocker_type": "source_blocker"},
        recommendation={"recommended_use_case": "media_device"},
        restore_plan={"status": "planned", "summary": "metadata backup only"},
    )
    summary = engine.record_observation(
        session_dir=tmp_path / "devices" / "precise",
        profile=precise_profile,
        state=SessionState(session_id="precise-session", selected_strategy="hardened_existing_os"),
        assessment={"support_status": "actionable", "restore_path_feasible": False},
        build_plan={"os_path": "maintainable_hardened_path", "source_acquisition": {"status": "missing_source"}},
        build_artifacts={"status": "missing_source", "details": {"missing_requirements": ["firmware"]}},
        blocker={"blocker_type": "source_blocker"},
        recommendation={"recommended_use_case": "media_device"},
        restore_plan={"status": "planned", "summary": "metadata backup only"},
    )

    precise_lookup = engine.lookup(precise_profile)
    coarse_lookup = engine.lookup(coarse_profile)

    assert summary["product_key"] == "samsung:sm-t377w:gteslte"
    assert coarse_lookup["product_key"] == "samsung:sm-t377w:gteslte"
    assert precise_lookup["observations"] == 2
    assert "unknown:unknown:gteslte" in precise_lookup["aliases"]
    assert "coarse" in precise_lookup["product"]["sessions"]
    assert "precise" in precise_lookup["product"]["sessions"]


def test_product_memory_keeps_equally_specific_related_variants_separate(tmp_path: Path) -> None:
    engine = ProductMemoryEngine(tmp_path)
    first = _profile(model="SM-T377W", session_id="first-session")
    second = _profile(model="SM-T377V", session_id="second-session")

    for session_name, profile in (("first", first), ("second", second)):
        engine.record_observation(
            session_dir=tmp_path / "devices" / session_name,
            profile=profile,
            state=SessionState(session_id=profile.session_id, selected_strategy="hardened_existing_os"),
            assessment={"support_status": "actionable", "restore_path_feasible": False},
            build_plan={"os_path": "maintainable_hardened_path", "source_acquisition": {"status": "missing_source"}},
            build_artifacts={"status": "missing_source", "details": {"missing_requirements": ["firmware"]}},
            blocker={"blocker_type": "source_blocker"},
            recommendation={"recommended_use_case": "media_device"},
            restore_plan={"status": "planned", "summary": "metadata backup only"},
        )

    first_lookup = engine.lookup(first)
    second_lookup = engine.lookup(second)

    assert first_lookup["product_key"] == "samsung:sm-t377w:gteslte"
    assert second_lookup["product_key"] == "samsung:sm-t377v:gteslte"
    assert first_lookup["observations"] == 1
    assert second_lookup["observations"] == 1
    assert "samsung:sm-t377v:gteslte" in first_lookup["related_identities"]
    assert "samsung:sm-t377w:gteslte" in second_lookup["related_identities"]

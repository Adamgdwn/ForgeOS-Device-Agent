from __future__ import annotations

from pathlib import Path

from app.core.models import DeviceProfile, Transport
from app.core.strategy_memory import StrategyMemoryEngine


def _profile(session_id: str, model: str = "Pixel 8") -> DeviceProfile:
    return DeviceProfile(
        session_id=session_id,
        canonical_name=session_id,
        device_codename="akita",
        fingerprint=f"{session_id}-fingerprint",
        manufacturer="Google",
        model=model,
        serial=f"SER-{session_id}",
        android_version="14",
        transport=Transport.USB_ADB,
        bootloader_locked=False,
        verified_boot_state="orange",
    )


def test_strategy_memory_retrieves_similar_successful_attempts(tmp_path: Path) -> None:
    engine = StrategyMemoryEngine(tmp_path)
    engine.record_attempt(
        profile=_profile("session-1"),
        blocker_type="source_blocker",
        strategy_id="hardened_existing_os",
        proposal_id="remote_first",
        env_overrides={"FORGEOS_SOURCE_SELECTION_MODE": "remote_first"},
        source_candidates=[{"name": "update.zip", "score": 7.0}],
        source_choice="update.zip",
        decision="advance",
        advanced=True,
        score=12.0,
        elapsed_seconds=0.8,
        estimated_tokens=140,
    )
    engine.record_attempt(
        profile=_profile("session-2", model="Pixel 7"),
        blocker_type="source_blocker",
        strategy_id="hardened_existing_os",
        proposal_id="images_first",
        env_overrides={"FORGEOS_SOURCE_SELECTION_MODE": "images_first"},
        source_candidates=[{"name": "system.img", "score": 6.0}],
        source_choice="system.img",
        decision="discard",
        advanced=False,
        score=2.0,
        elapsed_seconds=1.2,
        estimated_tokens=180,
    )

    similar = engine.retrieve_similar(profile=_profile("session-3"), blocker_type="source_blocker", limit=2)

    assert similar
    assert similar[0]["proposal_id"] == "remote_first"
    assert similar[0]["advanced"] is True


def test_strategy_memory_ranks_sources_using_historical_choice(tmp_path: Path) -> None:
    engine = StrategyMemoryEngine(tmp_path)
    engine.record_attempt(
        profile=_profile("session-1"),
        blocker_type="source_blocker",
        strategy_id="hardened_existing_os",
        proposal_id="baseline",
        env_overrides={},
        source_candidates=[{"name": "pixel_update.zip", "score": 5.0}],
        source_choice="pixel_update.zip",
        decision="advance",
        advanced=True,
        score=9.0,
        elapsed_seconds=0.7,
        estimated_tokens=110,
    )

    ranked = engine.rank_source_candidates(
        profile=_profile("session-2"),
        blocker_type="source_blocker",
        candidates=[
            {"name": "generic_update.zip", "score": 5.0},
            {"name": "pixel_update.zip", "score": 5.0},
        ],
    )

    assert ranked[0]["name"] == "pixel_update.zip"
    assert (tmp_path / "knowledge" / "strategy_memory_snapshot.json").exists()

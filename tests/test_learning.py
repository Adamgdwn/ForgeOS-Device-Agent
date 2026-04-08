import json
from pathlib import Path

from app.core.knowledge import KnowledgeEngine
from app.core.models import DeviceProfile, SessionState, SessionStateName, SupportStatus, Transport
from app.core.promotion import PromotionEngine


def _profile(session_id: str) -> DeviceProfile:
    return DeviceProfile(
        session_id=session_id,
        canonical_name=session_id,
        device_codename="pixel-test",
        fingerprint=f"{session_id}-fingerprint",
        manufacturer="Google",
        model="Pixel 8",
        serial=session_id,
        transport=Transport.USB_ADB,
    )


def _state(strategy: str, status: SupportStatus) -> SessionState:
    return SessionState(
        session_id="unused",
        state=SessionStateName.PATH_SELECT,
        selected_strategy=strategy,
        support_status=status,
    )


def _write_experiments(base: Path, session_id: str, fitness_score: float) -> Path:
    session_dir = base / "devices" / session_id
    reports_dir = session_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "autonomous-experiments.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "fitness": {
                    "fitness_score": fitness_score,
                    "advanced_count": 1,
                    "total_experiments": 1,
                    "human_intervention_count": 0,
                },
                "experiments": [],
            }
        )
    )
    return session_dir


def test_knowledge_engine_builds_support_matrix(tmp_path: Path) -> None:
    engine = KnowledgeEngine(tmp_path)
    for idx in range(3):
        session_dir = _write_experiments(tmp_path, f"session-{idx}", 1.0)
        engine.record_session_outcome(
            _profile(f"session-{idx}"),
            _state("hardened_existing_os", SupportStatus.ACTIONABLE),
            {
                "summary": "Assessment passed",
                "restore_path_feasible": True,
            },
            session_dir=session_dir,
        )

    matrix = json.loads((tmp_path / "knowledge" / "support_matrix.json").read_text())
    family = matrix["families"]["google:pixel-8"]
    assert family["observations"] == 3
    assert family["support_level"] == "provisionally_supported"
    assert family["recommended_strategy"] == "hardened_existing_os"
    assert family["average_fitness_score"] == 1.0


def test_promotion_engine_generates_review_candidate(tmp_path: Path) -> None:
    engine = KnowledgeEngine(tmp_path)
    for idx in range(3):
        session_dir = _write_experiments(tmp_path, f"session-{idx}", 1.0)
        engine.record_session_outcome(
            _profile(f"session-{idx}"),
            _state("hardened_existing_os", SupportStatus.ACTIONABLE),
            {
                "summary": "Assessment passed",
                "restore_path_feasible": True,
            },
            session_dir=session_dir,
        )

    promotion = PromotionEngine(tmp_path)
    payload = promotion.evaluate(engine.rebuild_support_matrix())
    assert payload["candidates"]
    assert payload["candidates"][0]["promotion_status"] == "review_required"

from __future__ import annotations

import json
from pathlib import Path

from app.core.retry_planner import RetryPlanner


def test_retry_planner_escalates_after_three_stalled_machine_solvable_cycles(tmp_path: Path) -> None:
    planner = RetryPlanner(tmp_path)
    session_dir = tmp_path / "devices" / "demo"
    (session_dir / "reports").mkdir(parents=True, exist_ok=True)
    heat_path = session_dir / "reports" / "retry-heat.json"
    heat_path.write_text(
        json.dumps(
            {
                "cycles": [
                    {"timestamp": "2026-01-01T00:00:00+00:00", "blocker_type": "source_blocker", "action_taken": "continue_autonomous_remediation", "advanced": False},
                    {"timestamp": "2026-01-01T00:01:00+00:00", "blocker_type": "source_blocker", "action_taken": "continue_autonomous_remediation", "advanced": False},
                    {"timestamp": "2026-01-01T00:02:00+00:00", "blocker_type": "source_blocker", "action_taken": "continue_autonomous_remediation", "advanced": False},
                ]
            }
        )
    )

    result = planner.build_plan(
        {"blocker_type": "source_blocker", "machine_solvable": True, "retry_budget": 2},
        session_dir=session_dir,
    )

    assert result["action"] == "escalate_strategy"


def test_retry_planner_halts_after_five_stalled_cycles(tmp_path: Path) -> None:
    planner = RetryPlanner(tmp_path)
    session_dir = tmp_path / "devices" / "demo"
    (session_dir / "reports").mkdir(parents=True, exist_ok=True)
    heat_path = session_dir / "reports" / "retry-heat.json"
    heat_path.write_text(
        json.dumps(
            {
                "cycles": [
                    {"timestamp": "2026-01-01T00:00:00+00:00", "blocker_type": "source_blocker", "action_taken": "continue_autonomous_remediation", "advanced": False},
                    {"timestamp": "2026-01-01T00:01:00+00:00", "blocker_type": "source_blocker", "action_taken": "continue_autonomous_remediation", "advanced": False},
                    {"timestamp": "2026-01-01T00:02:00+00:00", "blocker_type": "source_blocker", "action_taken": "continue_autonomous_remediation", "advanced": False},
                    {"timestamp": "2026-01-01T00:03:00+00:00", "blocker_type": "source_blocker", "action_taken": "escalate_strategy", "advanced": False},
                    {"timestamp": "2026-01-01T00:04:00+00:00", "blocker_type": "source_blocker", "action_taken": "escalate_strategy", "advanced": False},
                ]
            }
        )
    )

    result = planner.build_plan(
        {"blocker_type": "source_blocker", "machine_solvable": True, "retry_budget": 2},
        session_dir=session_dir,
    )

    assert result["action"] == "halt_and_review"


def test_retry_planner_mark_advanced_updates_last_cycle(tmp_path: Path) -> None:
    planner = RetryPlanner(tmp_path)
    session_dir = tmp_path / "devices" / "demo"
    (session_dir / "reports").mkdir(parents=True, exist_ok=True)

    planner.build_plan(
        {"blocker_type": "none", "machine_solvable": False, "retry_budget": 0},
        session_dir=session_dir,
    )
    planner.mark_advanced(session_dir)

    payload = json.loads((session_dir / "reports" / "retry-heat.json").read_text())
    assert payload["cycles"][-1]["advanced"] is True


def test_retry_planner_records_advance_experiment_when_blocker_improves(tmp_path: Path) -> None:
    planner = RetryPlanner(tmp_path)
    session_dir = tmp_path / "devices" / "demo"
    (session_dir / "reports").mkdir(parents=True, exist_ok=True)

    entry = planner.record_experiment(
        session_dir,
        blocker_before={"blocker_type": "source_blocker", "planned_next_action": "source_acquisition_and_staging", "summary": "Need firmware."},
        blocker_after={"blocker_type": "none"},
        inspection={"status": "solved", "evidence": {"source_acquisition": {"staged_files": ["/tmp/update.zip"]}}},
        generated={"task": {"task_id": "source-acquisition-and-staging", "remediation_family": "source_acquisition_and_staging"}},
    )

    payload = json.loads((session_dir / "reports" / "autonomous-experiments.json").read_text())
    assert entry["decision"] == "advance"
    assert payload["experiments"][-1]["decision"] == "advance"
    assert payload["experiments"][-1]["advanced"] is True


def test_retry_planner_records_discard_experiment_when_blocker_does_not_improve(tmp_path: Path) -> None:
    planner = RetryPlanner(tmp_path)
    session_dir = tmp_path / "devices" / "demo"
    (session_dir / "reports").mkdir(parents=True, exist_ok=True)

    entry = planner.record_experiment(
        session_dir,
        blocker_before={"blocker_type": "source_blocker", "planned_next_action": "source_acquisition_and_staging", "summary": "Need firmware."},
        blocker_after={"blocker_type": "source_blocker"},
        inspection={"status": "partial", "evidence": {"source_acquisition": {"staged_files": []}, "remote_source_resolution": {"status": "not_found"}}},
        generated={"task": {"task_id": "source-acquisition-and-staging", "remediation_family": "source_acquisition_and_staging"}},
    )

    payload = json.loads((session_dir / "reports" / "autonomous-experiments.json").read_text())
    assert entry["decision"] == "discard"
    assert payload["experiments"][-1]["advanced"] is False

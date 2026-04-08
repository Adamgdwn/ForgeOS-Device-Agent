from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.io_utils import atomic_write_json
from app.core.models import utc_now


class RetryPlanner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _heat_file(self, session_dir: Path) -> Path:
        return session_dir / "reports" / "retry-heat.json"

    def _experiment_file(self, session_dir: Path) -> Path:
        return session_dir / "reports" / "autonomous-experiments.json"

    def _load_heat(self, session_dir: Path) -> dict[str, Any]:
        path = self._heat_file(session_dir)
        if not path.exists():
            return {"cycles": []}
        try:
            payload = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            return {"cycles": []}
        return payload if isinstance(payload, dict) else {"cycles": []}

    def _write_heat(self, session_dir: Path, payload: dict[str, Any]) -> None:
        path = self._heat_file(session_dir)
        atomic_write_json(path, payload)

    def _load_experiments(self, session_dir: Path) -> dict[str, Any]:
        path = self._experiment_file(session_dir)
        if not path.exists():
            return {"experiments": []}
        try:
            payload = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            return {"experiments": []}
        return payload if isinstance(payload, dict) else {"experiments": []}

    def _write_experiments(self, session_dir: Path, payload: dict[str, Any]) -> None:
        path = self._experiment_file(session_dir)
        atomic_write_json(path, payload)

    @staticmethod
    def _blocker_id(blocker: dict[str, Any]) -> str:
        blocker_type = str(blocker.get("blocker_type") or "unknown")
        planned_next_action = str(blocker.get("planned_next_action") or "unspecified")
        summary = str(blocker.get("summary") or "").strip().lower().replace(" ", "_")[:48]
        return f"{blocker_type}:{planned_next_action}:{summary}".rstrip(":")

    def _session_fitness(self, experiments: list[dict[str, Any]]) -> dict[str, float | int]:
        if not experiments:
            return {
                "fitness_score": 0.0,
                "advanced_count": 0,
                "total_experiments": 0,
                "human_intervention_count": 0,
            }
        advanced_count = sum(1 for experiment in experiments if experiment.get("advanced") is True)
        human_intervention_count = sum(
            1 for experiment in experiments if experiment.get("human_intervention_required") is True
        )
        advance_ratio = advanced_count / len(experiments)
        autonomy_ratio = (len(experiments) - human_intervention_count) / len(experiments)
        return {
            "fitness_score": round(advance_ratio * autonomy_ratio, 3),
            "advanced_count": advanced_count,
            "total_experiments": len(experiments),
            "human_intervention_count": human_intervention_count,
        }

    @staticmethod
    def _blocker_rank(blocker_type: str | None) -> int:
        order = {
            "none": 0,
            "source_blocker": 1,
            "transport_blocker": 2,
            "subsystem_blocker": 3,
            "trust_blocker": 4,
            "physical_action_blocker": 5,
            "policy_blocker": 6,
        }
        return order.get(str(blocker_type or "unknown"), 7)

    def evaluate_experiment(
        self,
        *,
        blocker_before: dict[str, Any],
        blocker_after: dict[str, Any],
        inspection: dict[str, Any],
    ) -> dict[str, Any]:
        before_type = str(blocker_before.get("blocker_type", "none"))
        after_type = str(blocker_after.get("blocker_type", "none"))
        before_rank = self._blocker_rank(before_type)
        after_rank = self._blocker_rank(after_type)
        staged_files = (
            inspection.get("evidence", {})
            .get("source_acquisition", {})
            .get("staged_files", [])
        )
        remote_resolution = (
            inspection.get("evidence", {})
            .get("remote_source_resolution", {})
            .get("status", "")
        )
        status = str(inspection.get("status", "artifact_failed"))
        advanced = (
            after_rank < before_rank
            or after_type == "none"
            or bool(staged_files)
            or (
                before_type == after_type == "source_blocker"
                and remote_resolution == "ok"
            )
        )
        if advanced:
            decision = "advance"
            rationale = "The remediation changed the session enough to keep this direction."
        else:
            decision = "discard"
            rationale = "The remediation did not improve the blocker enough to keep this direction as an advance."
        return {
            "decision": decision,
            "advanced": advanced,
            "status": status,
            "blocker_before": before_type,
            "blocker_after": after_type,
            "staged_files": staged_files,
            "remote_resolution": remote_resolution,
            "rationale": rationale,
        }

    def record_experiment(
        self,
        session_dir: Path,
        *,
        blocker_before: dict[str, Any],
        blocker_after: dict[str, Any],
        inspection: dict[str, Any],
        generated: dict[str, Any] | None = None,
        elapsed_seconds: float | None = None,
        strategy: str | None = None,
        human_intervention_required: bool = False,
    ) -> dict[str, Any]:
        decision = self.evaluate_experiment(
            blocker_before=blocker_before,
            blocker_after=blocker_after,
            inspection=inspection,
        )
        payload = self._load_experiments(session_dir)
        experiments = list(payload.get("experiments") or [])
        entry = {
            "timestamp": utc_now(),
            "blocker_id": self._blocker_id(blocker_before),
            "task_id": (generated or {}).get("task", {}).get("task_id", ""),
            "remediation_family": (generated or {}).get("task", {}).get("remediation_family", ""),
            "planned_next_action": blocker_before.get("planned_next_action", ""),
            "summary": blocker_before.get("summary", ""),
            "selected_strategy": strategy or "",
            "elapsed_seconds": round(float(elapsed_seconds or 0.0), 3),
            "human_intervention_required": human_intervention_required,
            **decision,
        }
        experiments.append(entry)
        fitness = self._session_fitness(experiments)
        entry["session_fitness"] = fitness["fitness_score"]
        self._write_experiments(
            session_dir,
            {
                "generated_at": utc_now(),
                "fitness": fitness,
                "experiments": experiments,
            },
        )
        return experiments[-1]

    def build_plan(
        self,
        blocker: dict[str, Any],
        generated: dict[str, Any] | None = None,
        worker_self_heal: dict[str, Any] | None = None,
        session_dir: Path | None = None,
    ) -> dict[str, Any]:
        machine_solvable = blocker.get("machine_solvable", False)
        blocker_type = blocker.get("blocker_type")
        if blocker_type == "none":
            action = "return_to_main_plan"
            rationale = "The current blocker has been resolved enough for the runtime to continue the main execution path."
        elif machine_solvable:
            action = "continue_autonomous_remediation"
            rationale = "The blocker is machine-solvable, so the runtime should generate, execute, inspect, and reclassify before asking for help."
        elif blocker_type in {"trust_blocker", "physical_action_blocker"}:
            action = "await_user_action"
            rationale = "The next action depends on physical interaction or on-device approval."
        else:
            action = "halt_and_review"
            rationale = "The blocker is not safely solvable by autonomous retry."

        if session_dir is not None:
            heat = self._load_heat(session_dir)
            cycles = list(heat.get("cycles") or [])
            stall_count = 0
            for cycle in reversed(cycles):
                if cycle.get("blocker_type") != blocker_type or cycle.get("advanced") is True:
                    break
                stall_count += 1
            if stall_count >= 5:
                action = "halt_and_review"
                rationale = "The runtime stalled on the same blocker for five consecutive cycles and must stop for review."
            elif stall_count >= 3 and machine_solvable:
                action = "escalate_strategy"
                rationale = "The runtime stalled on the same machine-solvable blocker for three consecutive cycles and should escalate strategy."
            cycles.append(
                {
                    "timestamp": utc_now(),
                    "blocker_type": blocker_type,
                    "action_taken": action,
                    "advanced": False,
                }
            )
            self._write_heat(session_dir, {"cycles": cycles})

        return {
            "generated_at": utc_now(),
            "action": action,
            "rationale": rationale,
            "retry_budget": blocker.get("retry_budget", 0),
            "generated_files": (generated or {}).get("generated_files", []),
            "worker_self_heal": worker_self_heal or {},
        }

    def mark_advanced(self, session_dir: Path) -> None:
        heat = self._load_heat(session_dir)
        cycles = list(heat.get("cycles") or [])
        if not cycles:
            return
        cycles[-1]["advanced"] = True
        self._write_heat(session_dir, {"cycles": cycles})

    def write(self, session_dir: Path, payload: dict[str, Any]) -> Path:
        path = session_dir / "reports" / "retry-plan.json"
        return atomic_write_json(path, payload)

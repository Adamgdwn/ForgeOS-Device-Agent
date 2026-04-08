from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.io_utils import atomic_write_json
from app.core.models import DeviceProfile, SessionState, to_dict, utc_now
from app.core.policy_guard import PolicyGuard
from app.core.retry_planner import RetryPlanner
from app.core.strategy_memory import StrategyMemoryEngine


class SelfImprovementEngine:
    def __init__(
        self,
        root: Path,
        retry_planner: RetryPlanner,
        strategy_memory: StrategyMemoryEngine,
        policy_guard: PolicyGuard,
    ) -> None:
        self.root = root
        self.retry_planner = retry_planner
        self.strategy_memory = strategy_memory
        self.policy_guard = policy_guard

    def run_loop(
        self,
        *,
        session_dir: Path,
        generated_runtime: dict[str, Any],
        blocker_before: dict[str, Any],
        profile: DeviceProfile,
        state: SessionState,
        policy: Any,
        strategy_id: str,
        codegen_runtime: Any,
    ) -> dict[str, Any]:
        runtime_dir = session_dir / "runtime" / "self-improvement"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        blocker_type = str(blocker_before.get("blocker_type") or "none")
        retrieved = self.strategy_memory.retrieve_similar(profile=profile, blocker_type=blocker_type, limit=3)
        proposals = self._build_proposals(profile=profile, blocker_type=blocker_type, retrieved=retrieved)
        estimated_tokens_used = 0
        results: list[dict[str, Any]] = []

        for index, proposal in enumerate(proposals):
            transcript_name = f"artifact-execution-{proposal['proposal_id']}.json"
            estimated_tokens_used += self._estimate_candidate_tokens(generated_runtime, proposal)
            gate = self.policy_guard.evaluate_self_improvement_gate(
                policy=policy,
                session_dir=session_dir,
                estimated_tokens_used=estimated_tokens_used,
                iteration_count=index,
                proposed_paths=[runtime_dir / f"{proposal['proposal_id']}.json"],
            )
            if not gate.allowed:
                results.append(
                    {
                        "proposal": proposal,
                        "status": "blocked",
                        "inspection": {
                            "status": "policy_blocked",
                            "summary": gate.reason,
                            "evidence": {},
                        },
                        "score": -1.0,
                        "decision": "discard",
                        "advanced": False,
                        "governance_gate": to_dict(gate),
                    }
                )
                break

            execution = codegen_runtime.execute_generated(
                session_dir,
                generated_runtime,
                env_overrides=proposal["env_overrides"],
                transcript_name=transcript_name,
            )
            inspection = codegen_runtime.inspect_result(execution)
            experiment = self.retry_planner.evaluate_experiment(
                blocker_before=blocker_before,
                blocker_after={"blocker_type": inspection.get("next_blocker_type", blocker_before.get("blocker_type", "none"))},
                inspection=inspection,
            )
            score = self._score_result(inspection=inspection, experiment=experiment, estimated_tokens=estimated_tokens_used)
            results.append(
                {
                    "proposal": proposal,
                    "execution": execution,
                    "inspection": inspection,
                    "score": score,
                    "decision": experiment["decision"],
                    "advanced": experiment["advanced"],
                    "governance_gate": to_dict(gate),
                }
            )

        best_result = self._select_best_result(results)
        if best_result is None:
            blocked_gate = results[0].get("governance_gate", {}) if results else {}
            selected = {
                "proposal": proposals[0],
                "execution": {
                    "status": "policy_blocked",
                    "summary": "Governance policy blocked additional self-improvement attempts.",
                    "transcript_path": "",
                    "result": {},
                    "returncode": None,
                    "elapsed_seconds": 0.0,
                },
                "inspection": {
                    "status": "policy_blocked",
                    "summary": "Governance policy blocked additional self-improvement attempts.",
                    "evidence": {},
                },
                "score": -1.0,
                "decision": "discard",
                "advanced": False,
                "governance_gate": blocked_gate,
            }
        else:
            selected = best_result
        self._write_loop_manifest(runtime_dir, blocker_before, retrieved, results, selected)

        source_candidates = list(
            selected.get("inspection", {})
            .get("evidence", {})
            .get("source_acquisition", {})
            .get("local_candidates", [])
        )
        source_choice = ""
        staged_files = (
            selected.get("inspection", {})
            .get("evidence", {})
            .get("source_acquisition", {})
            .get("staged_files", [])
        )
        if staged_files:
            source_choice = Path(str(staged_files[0])).name
        self.strategy_memory.record_attempt(
            profile=profile,
            blocker_type=blocker_type,
            strategy_id=strategy_id or "unselected",
            proposal_id=selected["proposal"]["proposal_id"],
            env_overrides=selected["proposal"]["env_overrides"],
            source_candidates=source_candidates,
            source_choice=source_choice,
            decision=selected["decision"],
            advanced=selected["advanced"],
            score=float(selected["score"]),
            elapsed_seconds=float(selected.get("execution", {}).get("elapsed_seconds", 0.0) or 0.0),
            estimated_tokens=estimated_tokens_used,
        )
        return {
            "selected_proposal": selected["proposal"],
            "proposals": proposals,
            "results": results,
            "execution_result": selected["execution"],
            "inspection": selected["inspection"],
            "estimated_tokens_used": estimated_tokens_used,
            "retrieved_strategies": retrieved,
            "anomalies": [result["inspection"]["summary"] for result in results if result.get("status") == "blocked"],
        }

    def _build_proposals(
        self,
        *,
        profile: DeviceProfile,
        blocker_type: str,
        retrieved: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        proposals = [
            {
                "proposal_id": "baseline",
                "summary": "Use the generated remediation artifact as-is.",
                "env_overrides": {},
            }
        ]
        learned_keywords: list[str] = []
        for item in retrieved:
            learned_keywords.extend(
                term for term in str(item.get("source_choice") or "").replace(".", "_").split("_") if term
            )
        feature_tokens = "_".join(
            token for token in [
                (profile.manufacturer or "").lower(),
                (profile.model or "").lower(),
                (profile.device_codename or "").lower(),
            ]
            if token
        )
        if blocker_type == "source_blocker":
            proposals.extend(
                [
                    {
                        "proposal_id": "exact_match_local",
                        "summary": "Prioritize exact device-keyword local candidates before broader matches.",
                        "env_overrides": {
                            "FORGEOS_SOURCE_SELECTION_MODE": "exact_match",
                            "FORGEOS_PRIORITY_KEYWORDS": ",".join(learned_keywords[:6] or feature_tokens.split("_")),
                        },
                    },
                    {
                        "proposal_id": "images_first",
                        "summary": "Prefer fastboot-style images before sideload archives.",
                        "env_overrides": {
                            "FORGEOS_SOURCE_SELECTION_MODE": "images_first",
                            "FORGEOS_PRIORITY_KEYWORDS": ",".join(learned_keywords[:4]),
                        },
                    },
                    {
                        "proposal_id": "remote_first",
                        "summary": "Try trusted remote acquisition before local staging when local evidence is weak.",
                        "env_overrides": {
                            "FORGEOS_SOURCE_SELECTION_MODE": "remote_first",
                            "FORGEOS_PRIORITY_KEYWORDS": ",".join(learned_keywords[:4]),
                        },
                    },
                ]
            )
        else:
            proposals.append(
                {
                    "proposal_id": "low_cost_retry",
                    "summary": "Retry with low-cost preference and device-specific keywords.",
                    "env_overrides": {
                        "FORGEOS_PRIORITY_KEYWORDS": feature_tokens.replace("_", ","),
                    },
                }
            )
        for item in retrieved[:2]:
            env_overrides = dict(item.get("env_overrides") or {})
            if not env_overrides:
                continue
            proposals.append(
                {
                    "proposal_id": f"memory_{item['proposal_id']}",
                    "summary": "Replay a historically successful proposal from strategy memory.",
                    "env_overrides": env_overrides,
                }
            )
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for proposal in proposals:
            key = json.dumps(proposal["env_overrides"], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(proposal)
        return deduped

    def _estimate_candidate_tokens(self, generated_runtime: dict[str, Any], proposal: dict[str, Any]) -> int:
        source_len = len(json.dumps(generated_runtime.get("task", {})))
        proposal_len = len(json.dumps(proposal))
        return max(1, (source_len + proposal_len) // 4)

    def _score_result(self, *, inspection: dict[str, Any], experiment: dict[str, Any], estimated_tokens: int) -> float:
        staged_files = (
            inspection.get("evidence", {})
            .get("source_acquisition", {})
            .get("staged_files", [])
        )
        remote_ok = (
            inspection.get("evidence", {})
            .get("remote_source_resolution", {})
            .get("status", "")
            == "ok"
        )
        score = 0.0
        if experiment["advanced"]:
            score += 10.0
        if experiment["decision"] == "advance":
            score += 5.0
        if staged_files:
            score += 4.0
        if remote_ok:
            score += 2.0
        score -= estimated_tokens / 10000.0
        return round(score, 3)

    def _select_best_result(self, results: list[dict[str, Any]]) -> dict[str, Any] | None:
        viable = [result for result in results if result.get("status") != "blocked"]
        if not viable:
            return None
        viable.sort(
            key=lambda item: (
                -float(item.get("score", 0.0)),
                0 if item.get("advanced") else 1,
            )
        )
        return viable[0]

    def _write_loop_manifest(
        self,
        runtime_dir: Path,
        blocker_before: dict[str, Any],
        retrieved: list[dict[str, Any]],
        results: list[dict[str, Any]],
        selected: dict[str, Any],
    ) -> Path:
        payload = {
            "generated_at": utc_now(),
            "blocker_before": blocker_before,
            "retrieved_strategies": retrieved,
            "results": [
                {
                    "proposal": result.get("proposal"),
                    "score": result.get("score"),
                    "decision": result.get("decision"),
                    "advanced": result.get("advanced"),
                    "inspection_summary": result.get("inspection", {}).get("summary"),
                    "governance_gate": result.get("governance_gate", {}),
                }
                for result in results
            ],
            "selected_proposal": selected.get("proposal"),
        }
        return atomic_write_json(runtime_dir / "loop-manifest.json", payload)

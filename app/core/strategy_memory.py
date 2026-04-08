from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from app.core.io_utils import atomic_write_json
from app.core.models import DeviceProfile, utc_now


def _feature_tokens(profile: DeviceProfile, blocker_type: str) -> list[str]:
    values = [
        profile.manufacturer or "unknown",
        profile.model or "unknown",
        profile.android_version or "unknown",
        getattr(profile.transport, "value", str(profile.transport)),
        "locked" if profile.bootloader_locked else "unlocked" if profile.bootloader_locked is False else "bootloader_unknown",
        profile.verified_boot_state or "verified_boot_unknown",
        blocker_type or "none",
    ]
    slot_info = profile.slot_info or {}
    if slot_info:
        values.append(str(slot_info.get("active_slot") or "slot_unknown"))
        values.append("ab_device" if slot_info.get("a_b_device") else "single_slot")
    return [str(value).strip().lower().replace(" ", "_") for value in values if str(value).strip()]


def _vector_for(tokens: list[str], dims: int = 16) -> list[float]:
    vector = [0.0] * dims
    if not tokens:
        return vector
    for token in tokens:
        index = abs(hash(token)) % dims
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)


class StrategyMemoryEngine:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.knowledge_dir = root / "knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.knowledge_dir / "strategy_memory.sqlite3"
        self.snapshot_path = self.knowledge_dir / "strategy_memory_snapshot.json"
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    family_key TEXT NOT NULL,
                    blocker_type TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    feature_tokens TEXT NOT NULL,
                    feature_vector TEXT NOT NULL,
                    env_overrides TEXT NOT NULL,
                    source_candidates TEXT NOT NULL,
                    source_choice TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    advanced INTEGER NOT NULL,
                    score REAL NOT NULL,
                    elapsed_seconds REAL NOT NULL,
                    estimated_tokens INTEGER NOT NULL
                )
                """
            )

    def record_attempt(
        self,
        *,
        profile: DeviceProfile,
        blocker_type: str,
        strategy_id: str,
        proposal_id: str,
        env_overrides: dict[str, str],
        source_candidates: list[dict[str, Any]],
        source_choice: str,
        decision: str,
        advanced: bool,
        score: float,
        elapsed_seconds: float,
        estimated_tokens: int,
    ) -> None:
        tokens = _feature_tokens(profile, blocker_type)
        vector = _vector_for(tokens)
        family_key = f"{(profile.manufacturer or 'unknown').strip().lower().replace(' ', '-')}:{(profile.model or 'unknown').strip().lower().replace(' ', '-')}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_attempts (
                    recorded_at, session_id, family_key, blocker_type, strategy_id, proposal_id,
                    feature_tokens, feature_vector, env_overrides, source_candidates, source_choice,
                    decision, advanced, score, elapsed_seconds, estimated_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    profile.session_id,
                    family_key,
                    blocker_type,
                    strategy_id,
                    proposal_id,
                    json.dumps(tokens),
                    json.dumps(vector),
                    json.dumps(env_overrides, sort_keys=True),
                    json.dumps(source_candidates),
                    source_choice,
                    decision,
                    1 if advanced else 0,
                    float(score),
                    float(elapsed_seconds),
                    int(estimated_tokens),
                ),
            )
        self.write_snapshot()

    def retrieve_similar(
        self,
        *,
        profile: DeviceProfile,
        blocker_type: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        target_tokens = _feature_tokens(profile, blocker_type)
        target_vector = _vector_for(target_tokens)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM strategy_attempts
                WHERE blocker_type = ?
                ORDER BY recorded_at DESC
                LIMIT 100
                """,
                (blocker_type,),
            ).fetchall()
        scored: list[dict[str, Any]] = []
        for row in rows:
            feature_vector = json.loads(str(row["feature_vector"]))
            similarity = _cosine_similarity(target_vector, feature_vector)
            scored.append(
                {
                    "proposal_id": row["proposal_id"],
                    "strategy_id": row["strategy_id"],
                    "decision": row["decision"],
                    "advanced": bool(row["advanced"]),
                    "score": float(row["score"]),
                    "elapsed_seconds": float(row["elapsed_seconds"]),
                    "estimated_tokens": int(row["estimated_tokens"]),
                    "env_overrides": json.loads(str(row["env_overrides"])),
                    "source_candidates": json.loads(str(row["source_candidates"])),
                    "source_choice": str(row["source_choice"]),
                    "similarity": round(similarity, 4),
                }
            )
        scored.sort(
            key=lambda item: (
                -float(item["similarity"]),
                -float(item["score"]),
                0 if item["advanced"] else 1,
                float(item["elapsed_seconds"]),
            )
        )
        return scored[:limit]

    def rank_source_candidates(
        self,
        *,
        profile: DeviceProfile,
        blocker_type: str,
        candidates: list[dict[str, Any]],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        hints = self.retrieve_similar(profile=profile, blocker_type=blocker_type, limit=limit)
        preferred_terms: list[str] = []
        preferred_names: set[str] = set()
        for hint in hints:
            choice = str(hint.get("source_choice") or "").lower()
            if choice:
                preferred_names.add(choice)
                preferred_terms.extend(choice.replace(".", "_").split("_"))
        ranked: list[dict[str, Any]] = []
        for candidate in candidates:
            name = str(candidate.get("name") or candidate.get("filename") or candidate.get("url") or "").lower()
            score = float(candidate.get("score", 0.0))
            if name in preferred_names:
                score += 6.0
            score += sum(1.25 for term in preferred_terms if term and term in name)
            ranked.append({**candidate, "score": round(score, 3)})
        ranked.sort(key=lambda item: (-float(item.get("score", 0.0)), str(item.get("name") or item.get("url") or "")))
        return ranked

    def write_snapshot(self) -> Path:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT family_key, blocker_type, strategy_id, proposal_id, decision, advanced, score, source_choice, recorded_at
                FROM strategy_attempts
                ORDER BY recorded_at DESC
                LIMIT 50
                """
            ).fetchall()
        payload = {
            "generated_at": utc_now(),
            "attempts": [
                {
                    "family_key": row["family_key"],
                    "blocker_type": row["blocker_type"],
                    "strategy_id": row["strategy_id"],
                    "proposal_id": row["proposal_id"],
                    "decision": row["decision"],
                    "advanced": bool(row["advanced"]),
                    "score": float(row["score"]),
                    "source_choice": row["source_choice"],
                    "recorded_at": row["recorded_at"],
                }
                for row in rows
            ],
        }
        return atomic_write_json(self.snapshot_path, payload)

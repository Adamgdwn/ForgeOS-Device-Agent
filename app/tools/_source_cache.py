from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


SOURCE_CACHE_TTL_DAYS = 30


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def is_stale(research_path: Path) -> bool:
    """Return True if the research file is missing or older than TTL."""
    if not research_path.exists():
        return True
    try:
        payload = json.loads(research_path.read_text())
    except Exception:
        return True
    timestamp = _parse_timestamp(payload.get("fetched_at") or payload.get("generated_at"))
    if timestamp is None:
        return True
    now = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp < now - timedelta(days=SOURCE_CACHE_TTL_DAYS)


def touch_fetched_at(research_path: Path) -> None:
    """Update fetched_at to now without changing other fields."""
    if not research_path.exists():
        return
    payload = json.loads(research_path.read_text())
    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
    research_path.write_text(json.dumps(payload, indent=2))

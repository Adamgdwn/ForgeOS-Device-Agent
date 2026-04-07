from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.tools._source_cache import SOURCE_CACHE_TTL_DAYS, is_stale
from app.tools.source_resolver import SourceResolverTool


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


def test_source_cache_reports_stale_when_older_than_ttl(tmp_path: Path) -> None:
    research_path = tmp_path / "device_community.json"
    research_path.write_text(
        json.dumps(
            {
                "generated_at": (datetime.now(timezone.utc) - timedelta(days=SOURCE_CACHE_TTL_DAYS + 1)).isoformat()
            }
        )
    )

    assert is_stale(research_path) is True


def test_source_resolver_returns_stale_research(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "demo"
    research_path = session_dir / "research" / "device_community.json"
    research_path.parent.mkdir(parents=True, exist_ok=True)
    research_path.write_text(
        json.dumps(
            {
                "generated_at": (datetime.now(timezone.utc) - timedelta(days=SOURCE_CACHE_TTL_DAYS + 1)).isoformat(),
                "download_hints": ["https://download.lineageos.org/demo/update.zip"],
            }
        )
    )
    tool = SourceResolverTool(tmp_path)

    result = tool.run({"session_dir": str(session_dir), "research_path": str(research_path)})

    assert result["status"] == "stale_research"
    assert result["blocks"] is True


def test_source_resolver_downloads_trusted_direct_url(monkeypatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "demo"
    research_path = session_dir / "research" / "device_community.json"
    research_path.parent.mkdir(parents=True, exist_ok=True)
    research_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "download_hints": ["https://download.lineageos.org/demo/update.zip"],
            }
        )
    )
    tool = SourceResolverTool(tmp_path)
    monkeypatch.setattr(
        "app.tools.source_resolver.urlopen",
        lambda url, timeout=60: _FakeResponse(b"x" * (11 * 1024 * 1024)),
    )

    result = tool.run({"session_dir": str(session_dir), "research_path": str(research_path)})

    assert result["status"] == "ok"
    assert result["blocks"] is False
    assert Path(result["local_path"]).exists()

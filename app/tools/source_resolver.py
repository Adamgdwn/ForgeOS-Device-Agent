from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from app.tools.base import BaseTool
from app.tools._source_cache import is_stale, touch_fetched_at


class SourceResolverTool(BaseTool):
    name = "source_resolver"
    input_schema = {
        "session_dir": "string",
        "manufacturer": "string",
        "model": "string",
        "device_codename": "string",
        "research_path": "string",
        "target_os": "string",
    }
    output_schema = {"sources": "array", "status": "string"}

    _TRUSTED_HOST_SUFFIXES = (
        "google.com",
        "android.com",
        "lineageos.org",
        "twrp.me",
        "grapheneos.org",
        "calyxos.org",
        "github.com",
        "githubusercontent.com",
        "sourceforge.net",
    )

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    @staticmethod
    def _extract_candidate_url(payload: dict[str, Any]) -> str:
        url_pattern = re.compile(r"https?://[^\s)>\"]+")
        for item in payload.get("download_hints", []) or []:
            match = url_pattern.search(str(item))
            if match:
                return match.group(0)
        for item in payload.get("firmware_sources", []) or []:
            if not isinstance(item, dict):
                continue
            match = url_pattern.search(str(item.get("url_hint", "")))
            if match:
                return match.group(0)
        return ""

    def _is_trusted_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in self._TRUSTED_HOST_SUFFIXES)

    @staticmethod
    def _filename_for(url: str) -> str:
        return Path(urlparse(url).path).name

    def _download(self, url: str, destination: Path) -> tuple[bool, str]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.with_suffix(destination.suffix + ".part")
        try:
            with urlopen(url, timeout=60) as response, tmp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=8 * 1024 * 1024)
            tmp_path.replace(destination)
            return True, ""
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("source_resolver download failed for %s: %s", url, exc)
            if tmp_path.exists():
                tmp_path.unlink()
            return False, str(exc)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        session_dir = Path(str(payload.get("session_dir") or ""))
        research_path_raw = str(payload.get("research_path") or "")
        if research_path_raw:
            research_path = Path(research_path_raw)
        else:
            research_dir = session_dir / "research"
            candidates = [
                research_dir / "firmware_sources.json",
                research_dir / "device_community.json",
            ]
            research_path = next((path for path in candidates if path.exists()), candidates[0])
        if not research_path.exists():
            return {"sources": [], "status": "missing_research", "blocks": True, "reason": "Research file is missing."}
        if is_stale(research_path):
            return {"sources": [], "status": "stale_research", "blocks": True, "stale": True}

        try:
            research = json.loads(research_path.read_text())
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("source_resolver could not parse %s: %s", research_path, exc)
            return {"sources": [], "status": "invalid_research", "blocks": True, "reason": str(exc)}

        url = self._extract_candidate_url(research)
        if not url:
            return {"sources": [], "status": "no_source_found", "blocks": True}
        if not self._is_trusted_url(url):
            return {"sources": [], "status": "untrusted_source", "blocks": True, "url": url}
        filename = self._filename_for(url)
        if "." not in filename:
            return {"sources": [], "status": "download_failed", "blocks": True, "url": url}

        stage_dir = session_dir / "artifacts" / "os-source"
        destination = stage_dir / filename
        ok, error = self._download(url, destination)
        if not ok:
            return {"sources": [], "status": "download_failed", "blocks": True, "url": url, "reason": error}
        if destination.stat().st_size <= 10 * 1024 * 1024:
            destination.unlink(missing_ok=True)
            return {"sources": [], "status": "bad_download", "blocks": True, "url": url}

        touch_fetched_at(research_path)
        return {
            "sources": [str(destination)],
            "status": "ok",
            "blocks": False,
            "local_path": str(destination),
            "staged_path": str(destination),
            "source_url": url,
        }

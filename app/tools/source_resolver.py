from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
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
    def _extract_candidate_urls(payload: dict[str, Any]) -> list[str]:
        url_pattern = re.compile(r"https?://[^\s)>\"]+")
        urls: list[str] = []
        for item in payload.get("download_hints", []) or []:
            match = url_pattern.search(str(item))
            if match:
                urls.append(match.group(0))
        for item in payload.get("firmware_sources", []) or []:
            if not isinstance(item, dict):
                continue
            match = url_pattern.search(str(item.get("url_hint", "")))
            if match:
                urls.append(match.group(0))
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            unique.append(url)
        return unique

    @staticmethod
    def _extract_urls_from_html(base_url: str, html: str) -> list[str]:
        href_pattern = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)
        raw = href_pattern.findall(html)
        raw.extend(re.findall(r"""https?://[^\s<>"']+""", html))
        urls: list[str] = []
        seen: set[str] = set()
        for item in raw:
            url = urljoin(base_url, item)
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
        return urls

    def _is_trusted_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in self._TRUSTED_HOST_SUFFIXES)

    @staticmethod
    def _filename_for(url: str) -> str:
        return Path(urlparse(url).path).name

    @staticmethod
    def _looks_flashable(url: str) -> bool:
        filename = Path(urlparse(url).path).name.lower()
        return any(
            filename.endswith(suffix)
            for suffix in [
                ".zip",
                ".img",
                ".tar",
                ".tar.gz",
                ".tgz",
            ]
        )

    @staticmethod
    def _url_score(url: str, *, priority_terms: list[str]) -> float:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        filename = Path(parsed.path).name.lower()
        score = 0.0
        if any(filename.endswith(suffix) for suffix in [".zip", ".img", ".bin", ".tar", ".gz"]):
            score += 4.0
        if "lineage" in host or "android" in host or "google" in host:
            score += 2.5
        for term in priority_terms:
            if term and term in filename:
                score += 1.75
        return score

    def _candidate_pages(self, *, manufacturer: str, model: str, codename: str) -> list[str]:
        terms = [term for term in [codename, model.replace(" ", ""), model] if term]
        pages: list[str] = []
        if codename:
            pages.extend(
                [
                    f"https://wiki.lineageos.org/devices/{codename}/",
                    f"https://download.lineageos.org/devices/{codename}/builds",
                    f"https://twrp.me/search/?q={codename}",
                ]
            )
        for term in terms[:3]:
            pages.extend(
                [
                    f"https://sourceforge.net/projects/lineageos-for-{term}/files/",
                    f"https://github.com/search?q={term}+android+rom+releases&type=repositories",
                ]
            )
        unique: list[str] = []
        seen: set[str] = set()
        for page in pages:
            if page in seen:
                continue
            seen.add(page)
            unique.append(page)
        return unique

    def _discover_online_candidate_urls(
        self,
        *,
        manufacturer: str,
        model: str,
        codename: str,
    ) -> list[str]:
        discovered: list[str] = []
        seen: set[str] = set()
        for page in self._candidate_pages(manufacturer=manufacturer, model=model, codename=codename):
            if not self._is_trusted_url(page):
                continue
            try:
                with urlopen(page, timeout=30) as response:
                    html = response.read(2 * 1024 * 1024).decode("utf-8", errors="ignore")
            except Exception as exc:  # noqa: BLE001
                self.logger.info("source_resolver discovery skipped %s: %s", page, exc)
                continue
            for url in self._extract_urls_from_html(page, html):
                if not self._is_trusted_url(url) or not self._looks_flashable(url):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                discovered.append(url)
        return discovered

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

    def _device_context(self, payload: dict[str, object], session_dir: Path) -> dict[str, str]:
        profile_path = session_dir / "device-profile.json"
        profile: dict[str, Any] = {}
        if profile_path.exists():
            try:
                loaded = json.loads(profile_path.read_text())
                profile = loaded if isinstance(loaded, dict) else {}
            except Exception:  # noqa: BLE001
                profile = {}
        return {
            "manufacturer": str(payload.get("manufacturer") or profile.get("manufacturer") or ""),
            "model": str(payload.get("model") or profile.get("model") or ""),
            "device_codename": str(
                payload.get("device_codename")
                or profile.get("device_codename")
                or profile.get("raw_probe_data", {}).get("raw_event", {}).get("device_codename")
                or ""
            ),
        }

    def _write_build_request(
        self,
        *,
        session_dir: Path,
        device_context: dict[str, str],
        ranked_candidates: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        build_dir = session_dir / "runtime" / "build-from-source"
        build_dir.mkdir(parents=True, exist_ok=True)
        codename = device_context.get("device_codename", "")
        model = device_context.get("model", "")
        request = {
            "status": "build_required",
            "reason": reason,
            "manufacturer": device_context.get("manufacturer", ""),
            "model": model,
            "device_codename": codename,
            "recommended_builder": "lineageos" if codename else "aosp_generic",
            "ranked_download_candidates": ranked_candidates[:8],
            "required_outputs": [
                "OTA/recovery ZIP suitable for adb sideload",
                "or fastboot image set containing boot/system/vendor/super images as applicable",
            ],
            "commands": [
                "Install Android build prerequisites for this host.",
                "Initialize the selected Android/LineageOS source tree.",
                f"Sync device sources for `{codename or model or 'target device'}`.",
                "Build a signed or test-signed recovery package or fastboot image set.",
                "Place the produced artifacts under artifacts/os-source/ for automatic staging.",
            ],
        }
        request_path = build_dir / "source-build-request.json"
        request_path.write_text(json.dumps(request, indent=2))
        script_path = build_dir / "build_source_artifacts.sh"
        script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    "",
                    "# ForgeOS generated this build request because no trusted ready-made package met the threshold.",
                    "# Fill in any device-specific manifests/remotes required by the selected ROM project, then run from a prepared Android build host.",
                    f"DEVICE_CODENAME={json.dumps(codename)}",
                    f"OUTPUT_DIR={json.dumps(str(session_dir / 'artifacts' / 'os-source'))}",
                    "mkdir -p \"${OUTPUT_DIR}\"",
                    "echo \"Build source artifacts for ${DEVICE_CODENAME:-the target device}, then copy OTA ZIPs or fastboot images into ${OUTPUT_DIR}.\"",
                ]
            )
            + "\n"
        )
        script_path.chmod(0o755)
        build_attempt = self._run_configured_source_build(
            session_dir=session_dir,
            device_context=device_context,
        )
        return {
            "request_path": str(request_path),
            "script_path": str(script_path),
            "build_attempt": build_attempt,
            "request": request,
        }

    def _run_configured_source_build(
        self,
        *,
        session_dir: Path,
        device_context: dict[str, str],
    ) -> dict[str, Any]:
        if os.environ.get("FORGEOS_ALLOW_SOURCE_BUILDS", "0") != "1":
            return {
                "status": "not_configured",
                "reason": "Set FORGEOS_ALLOW_SOURCE_BUILDS=1 and FORGEOS_ANDROID_BUILD_COMMAND to let ForgeOS launch a local source build.",
            }
        command = os.environ.get("FORGEOS_ANDROID_BUILD_COMMAND", "").strip()
        if not command:
            return {
                "status": "not_configured",
                "reason": "FORGEOS_ANDROID_BUILD_COMMAND is not set.",
            }
        source_dir = session_dir / "artifacts" / "os-source"
        source_dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "FORGEOS_SESSION_DIR": str(session_dir),
            "FORGEOS_SOURCE_OUTPUT_DIR": str(source_dir),
            "FORGEOS_DEVICE_CODENAME": device_context.get("device_codename", ""),
            "FORGEOS_DEVICE_MODEL": device_context.get("model", ""),
        }
        try:
            completed = subprocess.run(
                command,
                cwd=session_dir,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=int(os.environ.get("FORGEOS_ANDROID_BUILD_TIMEOUT_SECONDS", "28800")),
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "failed",
                "returncode": -1,
                "stdout": str(exc.stdout or "")[-4000:],
                "stderr": "source build timed out",
                "staged_files": self._built_outputs(source_dir),
            }
        outputs = self._built_outputs(source_dir)
        return {
            "status": "completed" if completed.returncode == 0 and outputs else "failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "staged_files": outputs,
        }

    def _built_outputs(self, source_dir: Path) -> list[str]:
        if not source_dir.exists():
            return []
        outputs: list[str] = []
        for path in sorted(source_dir.iterdir()):
            if not path.is_file():
                continue
            name = path.name.lower()
            if not any(name.endswith(suffix) for suffix in [".zip", ".img", ".tar", ".tar.gz", ".tgz"]):
                continue
            if path.stat().st_size <= 10 * 1024 * 1024:
                continue
            outputs.append(str(path))
        return outputs

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        session_dir = Path(str(payload.get("session_dir") or ""))
        device_context = self._device_context(payload, session_dir)
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
        research: dict[str, Any] = {}
        if not research_path.exists() and not any(device_context.values()):
            return {"sources": [], "status": "missing_research", "blocks": True, "reason": "Research file is missing."}
        if research_path.exists() and is_stale(research_path):
            return {"sources": [], "status": "stale_research", "blocks": True, "stale": True}

        if research_path.exists():
            try:
                loaded = json.loads(research_path.read_text())
                research = loaded if isinstance(loaded, dict) else {}
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("source_resolver could not parse %s: %s", research_path, exc)
                return {"sources": [], "status": "invalid_research", "blocks": True, "reason": str(exc)}

        priority_terms = [
            re.sub(r"[^a-z0-9]+", "", str(device_context.get("manufacturer") or "").lower()),
            re.sub(r"[^a-z0-9]+", "", str(device_context.get("model") or "").lower()),
            re.sub(r"[^a-z0-9]+", "", str(device_context.get("device_codename") or "").lower()),
        ]
        urls = self._extract_candidate_urls(research)
        urls.extend(
            self._discover_online_candidate_urls(
                manufacturer=device_context.get("manufacturer", ""),
                model=device_context.get("model", ""),
                codename=device_context.get("device_codename", ""),
            )
        )
        urls = list(dict.fromkeys(urls))
        ranked_urls = [
            {
                "url": url,
                "filename": self._filename_for(url),
                "trusted": self._is_trusted_url(url),
                "score": self._url_score(url, priority_terms=priority_terms),
            }
            for url in urls
        ]
        ranked_urls = [item for item in ranked_urls if item["trusted"]]
        ranked_urls.sort(key=lambda item: (-float(item["score"]), str(item["filename"])))
        if not ranked_urls:
            build_request = self._write_build_request(
                session_dir=session_dir,
                device_context=device_context,
                ranked_candidates=[],
                reason="No trusted downloadable ROM or firmware package was discovered.",
            )
            build_attempt = build_request.get("build_attempt", {})
            if build_attempt.get("staged_files"):
                return {
                    "sources": list(build_attempt["staged_files"]),
                    "status": "ok",
                    "blocks": False,
                    "local_path": str(build_attempt["staged_files"][0]),
                    "staged_path": str(build_attempt["staged_files"][0]),
                    "source_url": "",
                    "ranked_candidates": [],
                    "build_request": build_request,
                }
            return {
                "sources": [],
                "status": "build_required",
                "blocks": True,
                "build_request": build_request,
            }
        url = str(ranked_urls[0]["url"])
        filename = self._filename_for(url)
        if "." not in filename:
            build_request = self._write_build_request(
                session_dir=session_dir,
                device_context=device_context,
                ranked_candidates=ranked_urls,
                reason="Best trusted candidate did not resolve to a flashable artifact filename.",
            )
            return {"sources": [], "status": "build_required", "blocks": True, "url": url, "ranked_candidates": ranked_urls, "build_request": build_request}

        stage_dir = session_dir / "artifacts" / "os-source"
        destination = stage_dir / filename
        ok, error = self._download(url, destination)
        if not ok:
            build_request = self._write_build_request(
                session_dir=session_dir,
                device_context=device_context,
                ranked_candidates=ranked_urls,
                reason=f"Best trusted candidate could not be downloaded: {error}",
            )
            return {"sources": [], "status": "build_required", "blocks": True, "url": url, "reason": error, "ranked_candidates": ranked_urls, "build_request": build_request}
        if destination.stat().st_size <= 10 * 1024 * 1024:
            destination.unlink(missing_ok=True)
            build_request = self._write_build_request(
                session_dir=session_dir,
                device_context=device_context,
                ranked_candidates=ranked_urls,
                reason="Best trusted candidate downloaded, but it was too small to trust as a flashable OS artifact.",
            )
            return {"sources": [], "status": "build_required", "blocks": True, "url": url, "ranked_candidates": ranked_urls, "build_request": build_request}

        touch_fetched_at(research_path)
        return {
            "sources": [str(destination)],
            "status": "ok",
            "blocks": False,
            "local_path": str(destination),
            "staged_path": str(destination),
            "source_url": url,
            "ranked_candidates": ranked_urls,
        }

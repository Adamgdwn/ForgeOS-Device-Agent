from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


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
    "samfw.com",
    "firmwarefile.com",
)

_LINEAGEOS_API = "https://download.lineageos.org/api/v1/device/{codename}/builds/nightly"
_TWRP_BASE = "https://dl.twrp.me/{codename}/"
_PHHUSSON_GSI_API = "https://api.github.com/repos/phhusson/treble_experimentations/releases/latest"
_SAMFW_BASE = "https://samfw.com/firmware/{model}/"
_CHUNK = 1 << 20  # 1 MiB
_TIMEOUT = 30

# Samsung model → region that typically has unlocked bootloader ROMs
_SAMSUNG_OPEN_REGIONS = ["XAR", "XAC", "BTU", "DBT", "OJV"]


class FirmwareDownloader:
    """Finds and downloads firmware from trusted sources into artifacts/os-source/."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("forgeos.firmware_downloader")

    def resolve_and_download(
        self,
        codename: str,
        android_version: str,
        session_dir: Path,
    ) -> dict[str, object]:
        """
        Full pipeline: query LineageOS → TWRP → Gemma hint.
        Returns a result dict with keys: status, files, source.
        """
        dest = session_dir / "artifacts" / "os-source"
        dest.mkdir(parents=True, exist_ok=True)

        result = self._try_lineageos(codename, dest)
        if result:
            return {"status": "downloaded", "files": result, "source": "lineageos"}

        twrp_file = self._try_twrp(codename, dest)
        if twrp_file:
            return {"status": "downloaded", "files": [twrp_file], "source": "twrp"}

        gsi_file = self._try_gsi(android_version, dest)
        if gsi_file:
            return {"status": "downloaded", "files": [gsi_file], "source": "gsi_phhusson"}

        gemma_file = self._try_gemma_hint(codename, android_version, dest)
        if gemma_file:
            return {"status": "downloaded", "files": [gemma_file], "source": "gemma_hint"}

        self.logger.warning("No firmware found for %s via any source", codename)
        return {"status": "not_found", "files": [], "source": None}

    # ------------------------------------------------------------------
    # Source-specific fetchers
    # ------------------------------------------------------------------

    def _try_lineageos(self, codename: str, dest: Path) -> list[str]:
        url = _LINEAGEOS_API.format(codename=codename)
        builds = self._fetch_lineageos(codename)
        if not builds:
            return []
        latest = builds[0]
        dl_url = latest.get("url") or latest.get("download_url", "")
        if not dl_url or not self._is_trusted_host(dl_url):
            return []
        fname = dl_url.split("/")[-1] or f"lineageos-{codename}.zip"
        dest_path = dest / fname
        if dest_path.exists():
            self.logger.info("LineageOS build already staged: %s", fname)
            return [str(dest_path)]
        if self._download(dl_url, dest_path, min_size_mb=50):
            return [str(dest_path)]
        return []

    def _try_twrp(self, codename: str, dest: Path) -> str | None:
        img_url = self._fetch_twrp(codename)
        if not img_url or not self._is_trusted_host(img_url):
            return None
        fname = img_url.split("/")[-1] or f"twrp-{codename}.img"
        dest_path = dest / fname
        if dest_path.exists():
            return str(dest_path)
        if self._download(img_url, dest_path, min_size_mb=5):
            return str(dest_path)
        return None

    def _try_gsi(self, android_version: str, dest: Path) -> str | None:
        """Download a Project Treble GSI from phhusson — works on any Treble-compatible device."""
        try:
            req = urllib.request.Request(
                _PHHUSSON_GSI_API,
                headers={"User-Agent": "ForgeOS/1.0", "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                release = json.loads(resp.read().decode())
            assets = release.get("assets", [])
            # Prefer arm64 vanilla (no GApps) system image
            preferred_keywords = ["arm64", "vanilla", "system"]
            best = None
            for asset in assets:
                name = asset.get("name", "").lower()
                url = asset.get("browser_download_url", "")
                if not url or not name.endswith(".img.xz") and not name.endswith(".img"):
                    continue
                if all(k in name for k in preferred_keywords):
                    best = (url, asset["name"])
                    break
            if best is None:
                # Fallback: any arm64 image
                for asset in assets:
                    name = asset.get("name", "").lower()
                    url = asset.get("browser_download_url", "")
                    if "arm64" in name and url and self._is_trusted_host(url):
                        best = (url, asset["name"])
                        break
            if best is None:
                return None
            dl_url, fname = best
            dest_path = dest / fname
            if dest_path.exists():
                return str(dest_path)
            if self._download(dl_url, dest_path, min_size_mb=100):
                return str(dest_path)
        except Exception as exc:
            self.logger.debug("GSI fetch failed: %s", exc)
        return None

    def _try_gemma_hint(
        self, codename: str, android_version: str, dest: Path
    ) -> str | None:
        try:
            from app.core.gemma_engine import GemmaEngine

            engine = GemmaEngine()
            resp = engine.ask(
                f"Device codename: {codename}, Android version: {android_version}.\n"
                "Provide the best direct download URL for LineageOS or TWRP firmware "
                "for this device. Return JSON: {\"url\": \"<url>\"}",
                schema={"url": "string"},
            )
            url = resp.get("url", "")
            if not url or not self._is_trusted_host(url):
                return None
            fname = url.split("/")[-1] or f"firmware-{codename}.zip"
            dest_path = dest / fname
            if self._download(url, dest_path, min_size_mb=5):
                return str(dest_path)
        except Exception as exc:
            self.logger.warning("Gemma firmware hint failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_lineageos(self, codename: str) -> list[dict]:
        url = _LINEAGEOS_API.format(codename=codename)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ForgeOS/1.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            builds = data if isinstance(data, list) else data.get("response", [])
            return builds or []
        except Exception as exc:
            self.logger.debug("LineageOS API query failed for %s: %s", codename, exc)
            return []

    def _fetch_twrp(self, codename: str) -> str | None:
        url = _TWRP_BASE.format(codename=codename)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ForgeOS/1.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            pattern = re.compile(r'href="([^"]+\.img)"', re.IGNORECASE)
            matches = pattern.findall(html)
            if not matches:
                return None
            # Take the most recent (last listed) .img link
            img_path = matches[-1]
            if img_path.startswith("http"):
                return img_path
            return f"https://dl.twrp.me{img_path}" if img_path.startswith("/") else f"{url}{img_path}"
        except Exception as exc:
            self.logger.debug("TWRP scrape failed for %s: %s", codename, exc)
            return None

    def _download(self, url: str, dest_path: Path, min_size_mb: float = 5) -> bool:
        min_bytes = int(min_size_mb * 1024 * 1024)
        self.logger.info("Downloading %s → %s", url, dest_path.name)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ForgeOS/1.0"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                tmp = dest_path.with_suffix(".part")
                written = 0
                with tmp.open("wb") as fh:
                    while True:
                        chunk = resp.read(_CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        written += len(chunk)
            if written < min_bytes:
                self.logger.warning(
                    "Download too small (%d bytes, expected ≥%d): %s",
                    written, min_bytes, url,
                )
                tmp.unlink(missing_ok=True)
                return False
            tmp.replace(dest_path)
            self.logger.info("Staged %s (%.1f MiB)", dest_path.name, written / 1024 / 1024)
            return True
        except Exception as exc:
            self.logger.warning("Download failed for %s: %s", url, exc)
            return False

    @staticmethod
    def _is_trusted_host(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == s or host.endswith(f".{s}") for s in _TRUSTED_HOST_SUFFIXES)

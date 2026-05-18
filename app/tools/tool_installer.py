from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path


_TOOL_MAP: dict[str, dict[str, str | None]] = {
    "adb":      {"apt": "android-tools-adb",   "pip": None,         "snap": None},
    "fastboot": {"apt": "android-tools-fastboot","pip": None,        "snap": None},
    "heimdall": {"apt": "heimdall-flash",        "pip": None,        "snap": None},
    "simg2img": {"apt": "android-tools-fstools", "pip": None,        "snap": None},
    "brotli":   {"apt": "brotli",                "pip": None,        "snap": None},
    "lz4":      {"apt": "lz4",                   "pip": None,        "snap": None},
    "e2fsck":   {"apt": "e2fsprogs",             "pip": None,        "snap": None},
    "ollama":   {"apt": None,                    "pip": None,        "snap": "ollama"},
    "goose":    {"apt": None,                    "pip": "goose-ai",  "snap": None},
}


class ToolInstaller:
    """Self-installs missing host tools via apt, pip, or snap."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("forgeos.tool_installer")

    def ensure(self, tool_name: str) -> bool:
        """Return True if the tool is available (installing if needed)."""
        if shutil.which(tool_name):
            return True
        info = _TOOL_MAP.get(tool_name)
        if not info:
            self.logger.warning("No install recipe for tool: %s", tool_name)
            return False
        if info.get("apt") and self.install_apt(info["apt"]):
            return shutil.which(tool_name) is not None
        if info.get("pip") and self.install_pip(info["pip"]):
            return shutil.which(tool_name) is not None
        if info.get("snap") and self.install_snap(info["snap"]):
            return shutil.which(tool_name) is not None
        self.logger.error("Could not install tool: %s", tool_name)
        return False

    def ensure_all(self, tools: list[str]) -> dict[str, bool]:
        """Ensure a list of tools are available. Returns {tool: ok} map."""
        return {tool: self.ensure(tool) for tool in tools}

    def install_apt(self, package: str) -> bool:
        self.logger.info("Installing via apt: %s", package)
        result = subprocess.run(
            ["sudo", "apt-get", "install", "-y", package],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode == 0:
            return True
        self.logger.warning("apt install failed for %s: %s", package, result.stderr[:200])
        return False

    def install_pip(self, package: str) -> bool:
        self.logger.info("Installing via pip: %s", package)
        result = subprocess.run(
            ["pip", "install", "--user", package],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode == 0:
            return True
        self.logger.warning("pip install failed for %s: %s", package, result.stderr[:200])
        return False

    def install_snap(self, package: str) -> bool:
        self.logger.info("Installing via snap: %s", package)
        result = subprocess.run(
            ["sudo", "snap", "install", package],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode == 0:
            return True
        self.logger.warning("snap install failed for %s: %s", package, result.stderr[:200])
        return False

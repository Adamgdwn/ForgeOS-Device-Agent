from __future__ import annotations

from pathlib import Path


def udev_supported() -> bool:
    return Path("/dev").exists() and Path("/sys").exists()

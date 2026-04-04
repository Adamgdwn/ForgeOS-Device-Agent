from __future__ import annotations

from pathlib import Path

from app.integrations.udev import udev_supported


class UdevListener:
    def __init__(self, root: Path) -> None:
        self.root = root

    def status(self) -> dict[str, object]:
        return {
            "supported": udev_supported(),
            "mode": "stub",
        }

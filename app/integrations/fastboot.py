from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.models import Transport


def _fastboot_path() -> str | None:
    local_fastboot = Path(__file__).resolve().parents[2] / "local-tools" / "platform-tools" / "fastboot"
    if local_fastboot.exists():
        return str(local_fastboot)
    return shutil.which("fastboot")


def fastboot_available() -> bool:
    return _fastboot_path() is not None


def list_devices() -> list[dict[str, str]]:
    if not fastboot_available():
        return []
    completed = subprocess.run(
        [_fastboot_path(), "devices"],
        capture_output=True,
        text=True,
        check=False,
    )
    devices: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        devices.append(
            {
                "serial": parts[0],
                "transport": Transport.USB_FASTBOOT.value,
            }
        )
    return devices

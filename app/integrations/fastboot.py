from __future__ import annotations

import shutil
import subprocess

from app.core.models import Transport


def fastboot_available() -> bool:
    return shutil.which("fastboot") is not None


def list_devices() -> list[dict[str, str]]:
    if not fastboot_available():
        return []
    completed = subprocess.run(
        ["fastboot", "devices"],
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

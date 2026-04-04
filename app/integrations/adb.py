from __future__ import annotations

import shutil
import subprocess

from app.core.models import Transport


def adb_available() -> bool:
    return shutil.which("adb") is not None


def list_devices() -> list[dict[str, str]]:
    if not adb_available():
        return []
    completed = subprocess.run(
        ["adb", "devices", "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    devices: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        if "\tdevice" not in line:
            continue
        serial = line.split()[0]
        devices.append(
            {
                "serial": serial,
                "transport": Transport.USB_ADB.value,
            }
        )
    return devices

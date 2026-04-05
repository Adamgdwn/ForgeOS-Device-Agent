from __future__ import annotations

import shutil
import subprocess

from app.core.models import Transport


def adb_available() -> bool:
    return shutil.which("adb") is not None


def list_devices() -> list[dict[str, str]]:
    if not adb_available():
        return []
    completed = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, check=False)
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


def raw_devices() -> list[dict[str, str]]:
    if not adb_available():
        return []
    completed = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, check=False)
    devices: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        if "\t" not in line:
            continue
        serial, remainder = line.split("\t", 1)
        status = remainder.split()[0]
        devices.append(
            {
                "serial": serial,
                "status": status,
                "line": line.strip(),
            }
        )
    return devices


def start_server() -> dict[str, object]:
    if not adb_available():
        return {"ok": False, "reason": "adb not available"}
    completed = subprocess.run(["adb", "start-server"], capture_output=True, text=True, check=False)
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
    }


def reconnect() -> dict[str, object]:
    if not adb_available():
        return {"ok": False, "reason": "adb not available"}
    completed = subprocess.run(["adb", "reconnect"], capture_output=True, text=True, check=False)
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
    }

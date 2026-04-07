from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from typing import Any

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
        serial = parts[0]
        device: dict[str, str] = {
            "serial": serial,
            "transport": Transport.USB_FASTBOOT.value,
        }
        # Enrich with getvar all so sessions for fastboot-mode devices start with
        # real manufacturer/model/codename rather than unknown-unknown.
        vars_result = describe_device_fastboot(serial)
        device.update(vars_result)
        devices.append(device)
    return devices


def describe_device_fastboot(serial: str) -> dict[str, str]:
    """Query key fastboot variables for the given device serial.

    Returns a dict with manufacturer, model, device_codename, android_version,
    and bootloader_locked so the session profile starts populated.
    """
    result = getvar_all(serial)
    out = str(result.get("stdout", ""))
    props: dict[str, str] = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        props[key.strip().lower()] = value.strip()

    manufacturer = (
        props.get("product.manufacturer")
        or props.get("manufacturer")
        or props.get("brand")
        or "Unknown"
    )
    model = (
        props.get("product.model")
        or props.get("product")
        or props.get("model")
        or "Unknown"
    )
    codename = (
        props.get("product.device")
        or props.get("product.name")
        or props.get("device")
        or ""
    )
    android_version = props.get("version.release") or ""
    bootloader_unlocked_raw = props.get("unlocked") or props.get("bootloader-unlocked") or ""
    bootloader_locked: bool | None = None
    if bootloader_unlocked_raw.lower() in {"yes", "true", "1"}:
        bootloader_locked = False
    elif bootloader_unlocked_raw.lower() in {"no", "false", "0"}:
        bootloader_locked = True

    result: dict[str, Any] = {
        "manufacturer": manufacturer,
        "model": model,
        "device_codename": codename,
        "android_version": android_version,
        "reachability": "fastboot-visible",
    }
    if bootloader_locked is not None:
        result["bootloader_locked"] = bootloader_locked
    return result


def run(args: list[str]) -> dict[str, object]:
    if not fastboot_available():
        return {"ok": False, "reason": "fastboot not available"}
    completed = subprocess.run(
        [_fastboot_path(), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
    }


def getvar_all(serial: str | None = None) -> dict[str, object]:
    args: list[str] = []
    if serial:
        args.extend(["-s", serial])
    args.extend(["getvar", "all"])
    return run(args)

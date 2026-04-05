from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core.models import Transport


def _adb_path() -> str | None:
    local_adb = Path(__file__).resolve().parents[2] / "local-tools" / "platform-tools" / "adb"
    if local_adb.exists():
        return str(local_adb)
    return shutil.which("adb")


def adb_available() -> bool:
    return _adb_path() is not None


def list_devices() -> list[dict[str, str]]:
    if not adb_available():
        return []
    completed = subprocess.run([_adb_path(), "devices", "-l"], capture_output=True, text=True, check=False)
    devices: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        metadata: dict[str, str] = {}
        for token in parts[2:]:
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            metadata[key] = value
        devices.append(
            {
                "serial": serial,
                "transport": Transport.USB_ADB.value,
                "product": metadata.get("product", ""),
                "model": metadata.get("model", ""),
                "device": metadata.get("device", ""),
            }
        )
    return devices


def raw_devices() -> list[dict[str, str]]:
    if not adb_available():
        return []
    completed = subprocess.run([_adb_path(), "devices", "-l"], capture_output=True, text=True, check=False)
    devices: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        if not line.strip() or line.startswith("List of devices attached"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, status = parts[0], parts[1]
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
    completed = subprocess.run([_adb_path(), "start-server"], capture_output=True, text=True, check=False)
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
    }


def reconnect() -> dict[str, object]:
    if not adb_available():
        return {"ok": False, "reason": "adb not available"}
    completed = subprocess.run([_adb_path(), "reconnect"], capture_output=True, text=True, check=False)
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "returncode": completed.returncode,
    }


def run(args: list[str]) -> dict[str, object]:
    if not adb_available():
        return {"ok": False, "reason": "adb not available"}
    completed = subprocess.run(
        [_adb_path(), *args],
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


def shell(serial: str, command: list[str]) -> dict[str, object]:
    if not adb_available():
        return {"ok": False, "reason": "adb not available"}
    completed = subprocess.run(
        [_adb_path(), "-s", serial, "shell", *command],
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


def pull(serial: str, remote_path: str, local_path: Path) -> dict[str, object]:
    if not adb_available():
        return {"ok": False, "reason": "adb not available"}
    local_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [_adb_path(), "-s", serial, "pull", remote_path, str(local_path)],
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


def getprop(serial: str, key: str) -> str:
    result = shell(serial, ["getprop", key])
    if not result.get("ok"):
        return ""
    return str(result.get("stdout", "")).strip()


def describe_device(serial: str) -> dict[str, str]:
    manufacturer = getprop(serial, "ro.product.manufacturer") or "Unknown"
    model = getprop(serial, "ro.product.model") or "Unknown"
    android_version = getprop(serial, "ro.build.version.release") or ""
    device_codename = getprop(serial, "ro.product.device") or ""
    return {
        "serial": serial,
        "transport": Transport.USB_ADB.value,
        "manufacturer": manufacturer.title() if manufacturer else "Unknown",
        "model": model,
        "android_version": android_version,
        "device_codename": device_codename,
        "reachability": "adb-visible",
    }


def hardware_snapshot(serial: str) -> dict[str, str]:
    keys = {
        "board": "ro.product.board",
        "hardware": "ro.hardware",
        "abi": "ro.product.cpu.abi",
        "fingerprint": "ro.build.fingerprint",
        "build_id": "ro.build.id",
        "security_patch": "ro.build.version.security_patch",
        "boot_slot": "ro.boot.slot_suffix",
        "bootloader": "ro.bootloader",
        "verified_boot_state": "ro.boot.verifiedbootstate",
        "dynamic_partitions": "ro.boot.dynamic_partitions",
    }
    snapshot = {name: getprop(serial, prop) for name, prop in keys.items()}
    battery = shell(serial, ["dumpsys", "battery"])
    snapshot["battery_dump"] = str(battery.get("stdout", "")).strip() if battery.get("ok") else ""
    return snapshot

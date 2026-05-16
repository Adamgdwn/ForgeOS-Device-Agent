from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _exe() -> str:
    return shutil.which("heimdall") or "heimdall"


def heimdall_available() -> bool:
    return shutil.which("heimdall") is not None


def _run(args: list[str], timeout: int = 120) -> dict[str, object]:
    if not heimdall_available():
        return {"ok": False, "reason": "heimdall not installed — run ToolInstaller().ensure('heimdall')"}
    try:
        completed = subprocess.run(
            [_exe(), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "returncode": completed.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"heimdall timed out after {timeout}s", "returncode": -1}
    except FileNotFoundError:
        return {"ok": False, "reason": "heimdall binary not found", "returncode": -1}


def detect() -> dict[str, object]:
    """Return ok=True if a device is present in Samsung Download Mode."""
    return _run(["detect"])


def print_pit() -> dict[str, object]:
    """Return the raw PIT (partition information table) from the device."""
    return _run(["print-pit", "--no-reboot"], timeout=30)


def flash(partitions: dict[str, str | Path], reboot: bool = True) -> dict[str, object]:
    """
    Flash one or more partitions.

    partitions: mapping of partition name → image file path
                e.g. {"BOOT": "/path/to/boot.img", "SYSTEM": "/path/to/system.img"}

    Returns the combined result of the heimdall flash invocation.
    """
    if not partitions:
        return {"ok": False, "reason": "no partitions specified"}
    args: list[str] = ["flash"]
    if not reboot:
        args.append("--no-reboot")
    for name, path in partitions.items():
        args.extend([f"--{name.upper()}", str(path)])
    return _run(args, timeout=600)


def reboot_device() -> dict[str, object]:
    """Send a reboot command via Heimdall (device must be in download mode)."""
    return _run(["close"], timeout=15)

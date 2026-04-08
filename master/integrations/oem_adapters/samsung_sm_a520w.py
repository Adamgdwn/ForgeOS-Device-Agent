from __future__ import annotations

import json
import sys
from pathlib import Path

# Device constants captured at first detection
ADAPTER_KEY = "samsung_sm_a520w"
MANUFACTURER = "Samsung"
MODEL = "SM-A520W"
CODENAME = "samsun-82d2"
ANDROID_VERSION = "8.0.0"
TRANSPORT = "usb-adb"
BOOTLOADER_LOCKED = None
AB_SLOTS = False
BOARD = ""
ABI = "arm64-v8a"

# Allow running directly or as part of the ForgeOS package tree.
# parents[3] resolves to the project root whether this file lives under
# devices/<session>/adapters/ or master/integrations/oem_adapters/.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.integrations import adb, fastboot  # noqa: E402


def probe(serial: str | None = None) -> dict[str, object]:
    """Check whether the device is visible over its expected transport."""
    if TRANSPORT in {"usb-adb", "usb-recovery"}:
        devices = adb.list_devices()
        for d in devices:
            if serial and d.get("serial") != serial:
                continue
            if (
                MODEL.upper() in d.get("model", "").upper()
                or CODENAME in d.get("device", "")
                or (serial and d.get("serial") == serial)
            ):
                return {"visible": True, "transport": TRANSPORT, "serial": d["serial"]}
        raw = adb.raw_devices()
        for d in raw:
            if d.get("status") == "unauthorized":
                return {"visible": True, "transport": "usb-unauthorized", "serial": d.get("serial", "")}
        return {"visible": False, "transport": TRANSPORT, "reason": "no adb device found for this model"}
    if TRANSPORT in {"usb-fastboot", "usb-fastbootd"}:
        devices = fastboot.list_devices()
        for d in devices:
            if serial and d.get("serial") != serial:
                continue
            return {"visible": True, "transport": TRANSPORT, "serial": d["serial"]}
        return {"visible": False, "transport": TRANSPORT, "reason": "no fastboot device found"}
    return {"visible": False, "transport": TRANSPORT, "reason": "unknown transport"}


def get_flash_commands(serial: str, artifact_path: str) -> list[dict[str, object]]:
    """Return ordered flash-command steps for this device and transport.

    All destructive steps carry requires_wipe_phrase=True so PolicyGuard can gate them.
    """
    steps: list[dict[str, object]] = []
    if TRANSPORT in {"usb-adb", "usb-recovery"}:
        steps.append({
            "step": "reboot_to_recovery",
            "command": ["adb", "-s", serial, "reboot", "recovery"],
            "description": "Reboot device into recovery for sideload.",
            "safe": True,
            "requires_approval": False,
            "requires_wipe_phrase": False,
        })
        steps.append({
            "step": "sideload",
            "command": ["adb", "-s", serial, "sideload", artifact_path],
            "description": "ADB sideload the recovery-compatible package.",
            "safe": False,
            "requires_approval": True,
            "requires_wipe_phrase": True,
        })
    elif TRANSPORT in {"usb-fastboot"}:
        slot = "_a" if AB_SLOTS else ""
        steps.append({
            "step": "flash_system",
            "command": ["fastboot", "-s", serial, "flash", f"system{slot}", artifact_path],
            "description": f"Flash system image to partition system{slot}.",
            "safe": False,
            "requires_approval": True,
            "requires_wipe_phrase": True,
        })
        if AB_SLOTS:
            steps.append({
                "step": "set_active_slot",
                "command": ["fastboot", "-s", serial, "--set-active=a"],
                "description": "Set active boot slot to A after flash.",
                "safe": True,
                "requires_approval": False,
                "requires_wipe_phrase": False,
            })
        steps.append({
            "step": "reboot",
            "command": ["fastboot", "-s", serial, "reboot"],
            "description": "Reboot device after flash.",
            "safe": True,
            "requires_approval": False,
            "requires_wipe_phrase": False,
        })
    return steps


def self_test() -> dict[str, object]:
    """Run probe and return a structured JSON result for promotion eligibility."""
    probe_result = probe()
    visible = bool(probe_result.get("visible"))
    status = "probe_pass" if visible else "probe_no_device"
    return {
        "status": status,
        "adapter_key": ADAPTER_KEY,
        "manufacturer": MANUFACTURER,
        "model": MODEL,
        "codename": CODENAME,
        "transport": TRANSPORT,
        "bootloader_locked": BOOTLOADER_LOCKED,
        "ab_slots": AB_SLOTS,
        "board": BOARD,
        "abi": ABI,
        "probe": probe_result,
        "summary": (
            f"Adapter {ADAPTER_KEY} probe confirmed device visible over {TRANSPORT}."
            if visible
            else f"Adapter {ADAPTER_KEY}: device not connected at self-test time (adapter is still valid)."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(self_test()))

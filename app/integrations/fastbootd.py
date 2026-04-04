from __future__ import annotations

from app.integrations.fastboot import list_devices as list_fastboot_devices


def list_devices() -> list[dict[str, str]]:
    devices = list_fastboot_devices()
    for device in devices:
        device["transport"] = "usb-fastbootd"
    return devices

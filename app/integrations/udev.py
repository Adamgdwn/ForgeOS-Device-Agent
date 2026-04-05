from __future__ import annotations

import subprocess
from pathlib import Path


def udev_supported() -> bool:
    return Path("/dev").exists() and Path("/sys").exists()


ANDROID_USB_HINTS = {
    "04e8": "Samsung",
    "18d1": "Google",
    "22b8": "Motorola",
    "0fce": "Sony",
    "2a70": "OnePlus",
    "2717": "Xiaomi",
    "2d95": "Nothing",
}


def list_usb_mobile_devices() -> list[dict[str, str]]:
    completed = subprocess.run(
        ["lsusb"],
        capture_output=True,
        text=True,
        check=False,
    )
    devices: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        if " ID " not in line:
            continue
        identifier = line.split(" ID ", 1)[1].split(" ", 1)[0]
        if ":" not in identifier:
            continue
        vendor_id, product_id = identifier.split(":", 1)
        vendor_hint = ANDROID_USB_HINTS.get(vendor_id.lower())
        lower = line.lower()
        likely_mobile = vendor_hint or "mtp" in lower or "galaxy" in lower or "android" in lower
        if not likely_mobile:
            continue
        devices.append(
            {
                "vendor_id": vendor_id.lower(),
                "product_id": product_id.lower(),
                "vendor_hint": vendor_hint or "Unknown",
                "description": line,
                "transport_hint": "usb-mtp" if "mtp" in lower else "usb-unknown",
            }
        )
    return devices

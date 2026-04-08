from __future__ import annotations

import subprocess
from pathlib import Path


def udev_supported() -> bool:
    return Path("/dev").exists() and Path("/sys").exists()


ANDROID_USB_HINTS = {
    # Alphabetical by brand for easy maintenance
    "2e04": "HMD/Nokia",
    "0bb4": "HTC",
    "12d1": "Huawei/Honor",
    "1004": "LG",
    "22b8": "Motorola",
    "2d95": "Nothing",
    "18d1": "Google",
    "22d9": "OPPO/Realme",
    "2a70": "OnePlus",
    "1d6b": "Fairphone",  # also generic Linux Foundation — filtered by description
    "0489": "Fairphone",
    "1bbb": "TCL/Alcatel",
    "04e8": "Samsung",
    "0fce": "Sony",
    "05c6": "Qualcomm/generic",  # used by many brands in EDL/fastboot mode
    "2717": "Xiaomi",
    "19d2": "ZTE",
    "2d9d": "Vivo",
    "17ef": "Lenovo/Motorola",
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
        # 1d6b is the Linux Foundation — used by hubs, controllers, etc.
        # Only treat it as Android if the description strongly suggests a phone.
        if vendor_id.lower() == "1d6b" and not any(k in lower for k in ("android", "mtp", "phone")):
            vendor_hint = None
        likely_mobile = vendor_hint or "mtp" in lower or "galaxy" in lower or "android" in lower or "phone" in lower
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

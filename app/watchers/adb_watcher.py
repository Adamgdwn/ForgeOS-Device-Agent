from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.event_bus import EventBus
from app.integrations import adb


class ADBWatcher:
    def __init__(self, root: Path, event_bus: EventBus, poll_interval: int = 3) -> None:
        self.root = root
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        self.seen_serials: set[str] = set()

    def run(self) -> None:
        self.logger.info("ADB watcher started")
        while True:
            for device in adb.list_devices():
                serial = device["serial"]
                if serial in self.seen_serials:
                    continue
                self.seen_serials.add(serial)
                enriched = adb.describe_device(serial)
                if not enriched.get("model") and device.get("model"):
                    enriched["model"] = device.get("model", "")
                if not enriched.get("device_codename") and device.get("device"):
                    enriched["device_codename"] = device.get("device", "")
                if device.get("product"):
                    enriched["product"] = device.get("product", "")
                # Capture full hardware snapshot at detection time so the session
                # profile starts with complete data for any device brand.
                hardware = adb.hardware_snapshot(serial)
                enriched["hardware_snapshot"] = hardware
                # Promote top-level fields from snapshot for easy access
                if not enriched.get("verified_boot_state"):
                    enriched["verified_boot_state"] = hardware.get("verified_boot_state")
                self.event_bus.publish("device_detected", enriched)
            time.sleep(self.poll_interval)

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.event_bus import EventBus
from app.integrations.udev import list_usb_mobile_devices


class USBWatcher:
    def __init__(self, root: Path, event_bus: EventBus, poll_interval: int = 3) -> None:
        self.root = root
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        self.seen_signatures: set[str] = set()

    def run(self) -> None:
        self.logger.info("USB watcher started")
        while True:
            for device in list_usb_mobile_devices():
                signature = f"{device.get('vendor_id')}:{device.get('product_id')}:{device.get('description')}"
                if signature in self.seen_signatures:
                    continue
                self.seen_signatures.add(signature)
                event = {
                    "manufacturer": device.get("vendor_hint", "Unknown"),
                    "model": "USB-attached Android",
                    "serial": f"usb-{device.get('vendor_id')}-{device.get('product_id')}",
                    "transport": device.get("transport_hint", "usb-mtp"),
                    "vendor_id": device.get("vendor_id"),
                    "product_id": device.get("product_id"),
                    "reachability": "usb-visible",
                    "usb_description": device.get("description"),
                }
                self.event_bus.publish("device_detected", event)
            time.sleep(self.poll_interval)

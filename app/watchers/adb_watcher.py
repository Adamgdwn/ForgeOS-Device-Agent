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
                self.event_bus.publish("device_detected", device)
            time.sleep(self.poll_interval)

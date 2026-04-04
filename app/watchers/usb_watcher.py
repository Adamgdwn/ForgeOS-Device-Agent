from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.event_bus import EventBus


class USBWatcher:
    def __init__(self, root: Path, event_bus: EventBus, poll_interval: int = 3) -> None:
        self.root = root
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self) -> None:
        self.logger.info("USB watcher started")
        while True:
            time.sleep(self.poll_interval)

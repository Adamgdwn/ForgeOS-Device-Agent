from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from app.core.bootstrap import run_bootstrap
from app.core.event_bus import EventBus
from app.core.logging_config import configure_logging
from app.core.orchestrator import ForgeOrchestrator
from app.core.policy import PolicyEngine
from app.gui.control_app import ForgeControlApp
from app.tools.vscode_opener import VSCodeOpenerTool
from app.watchers.adb_watcher import ADBWatcher
from app.watchers.fastboot_watcher import FastbootWatcher
from app.watchers.usb_watcher import USBWatcher


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    configure_logging(root / "logs", os.environ.get("FORGEOS_LOG_LEVEL", "INFO"))
    logger = logging.getLogger("forgeos")

    bootstrap_report = run_bootstrap(root)
    policy = PolicyEngine(root / "master" / "policies" / "default_policy.json").load()
    if policy.open_vscode_on_launch:
        VSCodeOpenerTool(root).execute(
            {
                "target_path": bootstrap_report["workspace_file"],
                "new_window": False,
            }
        )

    event_bus = EventBus()
    orchestrator = ForgeOrchestrator(root)
    event_bus.subscribe("device_detected", orchestrator.handle_device_event)

    watchers = [
        USBWatcher(root, event_bus, poll_interval=int(os.environ.get("FORGEOS_DEVICE_POLL_INTERVAL", "3"))),
        ADBWatcher(root, event_bus, poll_interval=int(os.environ.get("FORGEOS_DEVICE_POLL_INTERVAL", "3"))),
        FastbootWatcher(root, event_bus, poll_interval=int(os.environ.get("FORGEOS_DEVICE_POLL_INTERVAL", "3"))),
    ]

    threads = []
    for watcher in watchers:
        thread = threading.Thread(target=watcher.run, daemon=True)
        thread.start()
        threads.append(thread)

    logger.info("ForgeOS Device Agent started")
    app = ForgeControlApp(root, bootstrap_report)
    try:
        app.run()
    finally:
        logger.info("ForgeOS Device Agent stopping")


if __name__ == "__main__":
    main()

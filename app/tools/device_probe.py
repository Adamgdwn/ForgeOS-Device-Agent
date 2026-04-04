from __future__ import annotations

from pathlib import Path

from app.core.models import Transport
from app.tools.base import BaseTool


class DeviceProbeTool(BaseTool):
    name = "device_probe"
    input_schema = {"event": "object"}
    output_schema = {"device": "object"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        event = dict(payload.get("event", {}))
        transport = Transport(event.get("transport", Transport.UNKNOWN.value))
        serial = event.get("serial") or "unknown-serial"
        manufacturer = event.get("manufacturer") or "unknown"
        model = event.get("model") or "unknown"
        device = {
            "manufacturer": manufacturer,
            "model": model,
            "serial": serial,
            "android_version": event.get("android_version"),
            "bootloader_locked": event.get("bootloader_locked"),
            "verified_boot_state": event.get("verified_boot_state"),
            "slot_info": event.get("slot_info", {}),
            "battery": event.get("battery", {}),
            "transport": transport,
            "reachability": event.get("reachability", "detected"),
            "raw_event": event,
        }
        return {"device": device}

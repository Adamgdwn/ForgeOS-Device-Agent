from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _slugify(value: str | None) -> str:
    if not value:
        return "unknown"
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


class ConnectionPlaybookEngine:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.playbook_dir = root / "master" / "playbooks" / "connection"

    def resolve(
        self,
        manufacturer: str | None,
        model: str | None,
        engagement_status: str,
        transport: str,
    ) -> dict[str, Any]:
        candidates = [
            f"{_slugify(manufacturer)}-{_slugify(model)}.json",
            f"{_slugify(manufacturer)}.json",
            "generic-android.json",
        ]
        selected_path: Path | None = None
        data: dict[str, Any] = {}
        for candidate in candidates:
            path = self.playbook_dir / candidate
            if path.exists():
                selected_path = path
                data = json.loads(path.read_text())
                break

        states = data.get("states", {}) if data else {}
        state_key = self._state_key(engagement_status, transport)
        state_data = states.get(state_key, states.get("default", {}))
        return {
            "playbook_id": data.get("playbook_id", "generic-android"),
            "title": state_data.get("title", "Connection setup guidance"),
            "summary": state_data.get(
                "summary",
                "Follow the phone-side setup steps until ForgeOS sees adb, fastboot, or recovery transport.",
            ),
            "steps": state_data.get(
                "steps",
                [
                    "Unlock the phone.",
                    "Enable Developer Options.",
                    "Enable USB debugging.",
                    "Reconnect the USB cable if needed.",
                ],
            ),
            "expected_next_state": state_data.get("expected_next_state", "adb unauthorized"),
            "troubleshooting": state_data.get("troubleshooting", []),
            "source_path": str(selected_path) if selected_path else "",
            "state_key": state_key,
        }

    def _state_key(self, engagement_status: str, transport: str) -> str:
        if engagement_status == "awaiting_user_approval":
            return "adb_unauthorized"
        if engagement_status == "adb_connected":
            return "adb_connected"
        if engagement_status == "fastboot_connected":
            return "fastboot_connected"
        if transport == "usb-mtp" or engagement_status == "usb_only_detected":
            return "usb_only"
        return "default"

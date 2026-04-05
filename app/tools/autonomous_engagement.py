from __future__ import annotations

from pathlib import Path

from app.integrations import adb, fastboot, fastbootd
from app.integrations import udev
from app.tools.base import BaseTool


class AutonomousEngagementTool(BaseTool):
    name = "autonomous_engagement"
    input_schema = {"device": "object", "session_dir": "string"}
    output_schema = {"engagement_status": "string", "summary": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        device = dict(payload["device"])
        transport_value = device.get("transport", "unknown")
        transport = getattr(transport_value, "value", str(transport_value))

        actions_attempted: list[dict[str, object]] = []
        findings: list[str] = []

        start_result = adb.start_server()
        actions_attempted.append({"action": "adb_start_server", **start_result})

        if transport == "usb-adb":
            raw_adb = adb.raw_devices()
            findings.append("adb transport is available.")
            return {
                "engagement_status": "adb_connected",
                "summary": "ForgeOS has adb transport and can continue non-destructive assessment autonomously.",
                "actions_attempted": actions_attempted,
                "findings": findings,
                "raw_adb": raw_adb,
            }

        if transport in {"usb-fastboot", "usb-fastbootd"}:
            findings.append("fastboot transport is available.")
            return {
                "engagement_status": "fastboot_connected",
                "summary": "ForgeOS has fastboot transport and can continue low-level assessment autonomously.",
                "actions_attempted": actions_attempted,
                "findings": findings,
                "raw_fastboot": fastboot.list_devices() + fastbootd.list_devices(),
            }

        reconnect_result = adb.reconnect()
        actions_attempted.append({"action": "adb_reconnect", **reconnect_result})

        raw_adb = adb.raw_devices()
        if raw_adb:
            statuses = {entry["status"] for entry in raw_adb}
            if "unauthorized" in statuses:
                findings.append("Phone is visible to adb but still requires on-device trust approval.")
                return {
                    "engagement_status": "awaiting_user_approval",
                    "summary": "ForgeOS reached adb visibility, but the phone must approve this computer on-screen before autonomous assessment can continue.",
                    "actions_attempted": actions_attempted,
                    "findings": findings,
                    "raw_adb": raw_adb,
                    "next_steps": [
                        "Unlock the phone screen.",
                        "Accept the 'Allow USB debugging' prompt.",
                    ],
                }
            if "device" in statuses:
                findings.append("adb became available after autonomous reconnect attempts.")
                return {
                    "engagement_status": "adb_connected",
                    "summary": "ForgeOS autonomously recovered adb transport and can continue assessment.",
                    "actions_attempted": actions_attempted,
                    "findings": findings,
                    "raw_adb": raw_adb,
                }

        usb_devices = udev.list_usb_mobile_devices()
        if transport == "usb-mtp" or usb_devices:
            findings.append("Phone is attached by USB, but only USB/MTP-level visibility is available.")
            return {
                "engagement_status": "usb_only_detected",
                "summary": "ForgeOS can see the phone over USB and has attempted safe adb engagement, but the phone still needs adb, fastboot, or recovery transport exposed.",
                "actions_attempted": actions_attempted,
                "findings": findings,
                "usb_devices": usb_devices or [device],
                "next_steps": [
                    "Unlock the phone.",
                    "Enable Developer Options and USB debugging.",
                    "Approve the computer trust prompt if it appears.",
                    "Reconnect the cable if the phone remains in MTP-only mode.",
                ],
            }

        return {
            "engagement_status": "no_device_transport",
            "summary": "ForgeOS could not reach a manageable device transport during autonomous engagement.",
            "actions_attempted": actions_attempted,
            "findings": ["No adb, fastboot, or USB-only Android visibility was confirmed after engagement attempts."],
        }

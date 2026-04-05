from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class FeasibilityAssessorTool(BaseTool):
    name = "feasibility_assessor"
    input_schema = {"device": "object", "session_dir": "string"}
    output_schema = {"support_status": "string", "summary": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        device = dict(payload["device"])
        transport_value = device.get("transport", "unknown")
        transport = getattr(transport_value, "value", str(transport_value))
        bootloader_locked = device.get("bootloader_locked")
        serial = device.get("serial")

        blocked_reasons: list[str] = []
        if transport == "usb-mtp":
            return {
                "support_status": "research_only",
                "summary": "USB phone detected in MTP/media mode. ForgeOS can engage autonomously only after adb, fastboot, or recovery transport becomes available.",
                "restore_path_feasible": False,
                "recommended_path": "transport_engagement",
            }
        if serial in (None, "", "unknown-serial"):
            blocked_reasons.append("No stable serial detected")
        if transport == "unknown":
            blocked_reasons.append("Transport mode is unknown")

        if blocked_reasons:
            return {
                "support_status": "blocked",
                "summary": "; ".join(blocked_reasons),
                "restore_path_feasible": False,
                "recommended_path": "research_only",
            }

        if bootloader_locked is True:
            return {
                "support_status": "research_only",
                "summary": "Device detected, but bootloader remains locked until restore path and unlock policy are proven.",
                "restore_path_feasible": False,
                "recommended_path": "research_only",
            }

        return {
            "support_status": "actionable",
            "summary": "Assessment passed initial feasibility gates for non-destructive planning.",
            "restore_path_feasible": True,
            "recommended_path": "hardened_existing_os",
        }

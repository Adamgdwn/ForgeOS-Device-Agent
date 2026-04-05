from __future__ import annotations

import json
import tarfile
from pathlib import Path
from typing import Any

from app.integrations import adb
from app.tools.base import BaseTool


class BackupAndRestorePlannerTool(BaseTool):
    name = "backup_and_restore_planner"
    input_schema = {"device": "object", "session_dir": "string", "assessment": "object"}
    output_schema = {"restore_path_feasible": "boolean", "plan": "object"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        device = dict(payload["device"])
        session_dir = Path(str(payload["session_dir"]))
        assessment = dict(payload.get("assessment", {}))
        backup_dir = session_dir / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        serial = str(device.get("serial") or "")
        transport_value = device.get("transport", "unknown")
        transport = getattr(transport_value, "value", str(transport_value))
        metadata_capture: dict[str, Any] = {
            "transport": transport,
            "serial": serial,
            "adb_metadata_available": False,
            "captures": {},
            "limitations": [],
        }

        if transport == "usb-adb" and serial and serial != "unknown-serial":
            capture_commands = {
                "getprop": ["getprop"],
                "packages": ["pm", "list", "packages"],
                "battery": ["dumpsys", "battery"],
                "settings_secure": ["settings", "list", "secure"],
                "settings_global": ["settings", "list", "global"],
                "settings_system": ["settings", "list", "system"],
            }
            adb_ok = True
            for name, command in capture_commands.items():
                result = adb.shell(serial, command)
                metadata_capture["captures"][name] = {
                    "ok": result.get("ok", False),
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                }
                adb_ok = adb_ok and bool(result.get("ok"))
            metadata_capture["adb_metadata_available"] = adb_ok
            if not adb_ok:
                metadata_capture["limitations"].append(
                    "adb metadata capture was attempted, but some device queries failed."
                )
        else:
            metadata_capture["limitations"].append(
                "adb transport is not available, so only host-side session evidence can be backed up right now."
            )

        metadata_path = backup_dir / "device-metadata-backup.json"
        metadata_path.write_text(json.dumps(metadata_capture, indent=2))

        archive_path = backup_dir / "session-recovery-bundle.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            for relative in [
                "device-profile.json",
                "session-state.json",
                "user-profile.json",
                "os-goals.json",
                "reports",
                "plans",
                "codex",
            ]:
                target = session_dir / relative
                if target.exists():
                    tar.add(target, arcname=relative)

        restore_path_feasible = bool(assessment.get("restore_path_feasible"))
        if not restore_path_feasible and metadata_capture["adb_metadata_available"]:
            restore_path_feasible = True

        plan = {
            "status": "captured",
            "summary": (
                "Captured the best available pre-wipe backup evidence for this session."
            ),
            "backup_bundle_path": str(archive_path),
            "metadata_backup_path": str(metadata_path),
            "restore_path_feasible": restore_path_feasible,
            "transport": transport,
            "captured_with_adb": metadata_capture["adb_metadata_available"],
            "limitations": metadata_capture["limitations"],
            "restore_notes": (
                "This bundle always restores session intelligence and host-side evidence. "
                "Full device reinstall still depends on real flashing adapters and vendor images."
            ),
        }
        plan_path = backup_dir / "backup-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2))
        return {
            "restore_path_feasible": restore_path_feasible,
            "plan": plan,
            "backup_plan_path": str(plan_path),
        }

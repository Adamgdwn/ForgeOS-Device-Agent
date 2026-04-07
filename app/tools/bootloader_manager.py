from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.models import PolicyModel
from app.integrations import fastboot
from app.tools.base import BaseTool


class BootloaderManagerTool(BaseTool):
    name = "bootloader_manager"
    input_schema = {"device": "object", "action": "string"}
    output_schema = {"status": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        action = str(payload.get("action", "inspect"))
        device = dict(payload.get("device", {}))
        serial = str(device.get("serial") or "")
        raw_policy = payload.get("policy", {})
        policy = PolicyModel(**raw_policy) if isinstance(raw_policy, dict) else raw_policy

        if action == "inspect":
            return {
                "unlock_issued": False,
                "status": "inspect_only",
                "blocks": False,
                "action": action,
            }
        if action not in {"unlock", "unlock_critical"}:
            return {
                "unlock_issued": False,
                "status": "unsupported_action",
                "blocks": True,
                "action": action,
            }
        if not getattr(policy, "allow_live_destructive_actions", False):
            return {
                "unlock_issued": False,
                "status": "awaiting_policy_approval",
                "blocks": True,
                "action": action,
            }
        fastboot_path = fastboot._fastboot_path()
        if not fastboot_path:
            return {
                "unlock_issued": False,
                "status": "fastboot_unavailable",
                "blocks": True,
                "action": action,
            }

        command = [fastboot_path]
        if serial:
            command.extend(["-s", serial])
        command.extend(["flashing", "unlock"] if action == "unlock" else ["flashing", "unlock_critical"])

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("bootloader_manager failed for %s: %s", serial or "unknown", exc)
            return {
                "unlock_issued": False,
                "status": "command_failed",
                "blocks": True,
                "action": action,
                "reason": str(exc),
            }

        return {
            "unlock_issued": completed.returncode == 0,
            "status": "unlock_issued" if completed.returncode == 0 else "unlock_failed",
            "blocks": completed.returncode != 0,
            "action": action,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }

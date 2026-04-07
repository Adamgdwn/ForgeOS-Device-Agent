from __future__ import annotations

import subprocess
from pathlib import Path

from app.integrations import adb
from app.tools.base import BaseTool


class BootValidatorTool(BaseTool):
    name = "boot_validator"
    input_schema = {"device": "object"}
    output_schema = {"status": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    @staticmethod
    def _read_prop(adb_path: str, serial: str, key: str) -> tuple[str, str]:
        completed = subprocess.run(
            [adb_path, "-s", serial, "shell", "getprop", key],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return completed.stdout.strip(), completed.stderr.strip()

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        device = dict(payload.get("device", {}))
        serial = str(device.get("serial") or "")
        if not serial:
            return {
                "verified_boot_state": "",
                "bootloader_locked": False,
                "status": "missing_serial",
                "blocks": True,
            }
        adb_path = adb._adb_path()
        if not adb_path:
            return {
                "verified_boot_state": "",
                "bootloader_locked": False,
                "status": "adb_unavailable",
                "blocks": True,
            }
        try:
            verified_boot_state, verified_boot_stderr = self._read_prop(adb_path, serial, "ro.boot.verifiedbootstate")
            flash_locked_raw, flash_locked_stderr = self._read_prop(adb_path, serial, "ro.boot.flash.locked")
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("boot_validator failed for %s: %s", serial, exc)
            return {
                "verified_boot_state": "",
                "bootloader_locked": False,
                "status": "probe_failed",
                "blocks": True,
                "reason": str(exc),
            }

        bootloader_locked = flash_locked_raw.strip() == "1"
        passed = bool(verified_boot_state) and verified_boot_state.lower() in {"green", "yellow"} and bootloader_locked
        return {
            "verified_boot_state": verified_boot_state,
            "bootloader_locked": bootloader_locked,
            "status": "pass" if passed else "fail",
            "blocks": not passed,
            "stderr": "; ".join(item for item in [verified_boot_stderr, flash_locked_stderr] if item),
        }

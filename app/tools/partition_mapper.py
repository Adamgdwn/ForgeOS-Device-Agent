from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from app.integrations import adb

from app.tools.base import BaseTool


class PartitionMapperTool(BaseTool):
    name = "partition_mapper"
    input_schema = {"device": "object"}
    output_schema = {"partitions": "array"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    @staticmethod
    def _parse_partitions(stdout: str, mounts_by_device: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
        partitions: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) != 4 or parts[0] == "major":
                continue
            _, _, blocks, name = parts
            device_path = f"/dev/block/{name}"
            mount = mounts_by_device.get(device_path, {})
            try:
                size_kb = int(blocks)
            except ValueError:
                size_kb = 0
            partitions.append(
                {
                    "name": name,
                    "size_kb": size_kb,
                    "mount": mount.get("mount", ""),
                    "type": mount.get("type", ""),
                }
            )
        return partitions

    @staticmethod
    def _parse_mounts(stdout: str) -> dict[str, dict[str, str]]:
        mounts: dict[str, dict[str, str]] = {}
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            mounts[parts[0]] = {"mount": parts[1], "type": parts[2]}
        return mounts

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        device = dict(payload.get("device", {}))
        serial = str(device.get("serial") or "")
        if not serial:
            return {
                "partitions": [],
                "status": "missing_serial",
                "blocks": True,
                "reason": "partition_mapper requires a device serial to query partition metadata.",
            }
        adb_path = adb._adb_path()
        if not adb_path:
            return {
                "partitions": [],
                "status": "adb_unavailable",
                "blocks": True,
                "reason": "adb is not available on this host.",
            }

        try:
            partitions_result = subprocess.run(
                [adb_path, "-s", serial, "shell", "cat", "/proc/partitions"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            mounts_result = subprocess.run(
                [adb_path, "-s", serial, "shell", "cat", "/proc/mounts"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("partition_mapper failed for %s: %s", serial, exc)
            return {
                "partitions": [],
                "status": "command_failed",
                "blocks": True,
                "reason": str(exc),
            }

        if partitions_result.returncode != 0:
            return {
                "partitions": [],
                "status": "partition_probe_failed",
                "blocks": True,
                "reason": partitions_result.stderr.strip() or "Unable to read /proc/partitions via adb.",
            }

        mounts_by_device = self._parse_mounts(mounts_result.stdout if mounts_result.returncode == 0 else "")
        partitions = self._parse_partitions(partitions_result.stdout, mounts_by_device)
        return {
            "partitions": partitions,
            "status": "ok",
            "blocks": False,
        }

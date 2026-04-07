from __future__ import annotations

import subprocess
from pathlib import Path

from app.tools.avb_signer import AVBSignerTool
from app.tools.boot_validator import BootValidatorTool
from app.tools.bootloader_manager import BootloaderManagerTool
from app.tools.partition_mapper import PartitionMapperTool
from app.tools.source_resolver import SourceResolverTool


def test_partition_mapper_parses_partitions(monkeypatch, tmp_path: Path) -> None:
    tool = PartitionMapperTool(tmp_path)

    monkeypatch.setattr("app.tools.partition_mapper.adb._adb_path", lambda: "/usr/bin/adb")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[-1] == "/proc/partitions":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="major minor  #blocks  name\n179        0   7634944 mmcblk0\n179        1      65536 mmcblk0p1\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="/dev/block/mmcblk0p1 /boot emmc rw 0 0\n",
            stderr="",
        )

    monkeypatch.setattr("app.tools.partition_mapper.subprocess.run", fake_run)

    result = tool.run({"device": {"serial": "ABC123"}})

    assert result["status"] == "ok"
    assert result["blocks"] is False
    assert result["partitions"][1]["name"] == "mmcblk0p1"
    assert result["partitions"][1]["mount"] == "/boot"
    assert result["partitions"][1]["type"] == "emmc"


def test_bootloader_manager_respects_policy(tmp_path: Path) -> None:
    tool = BootloaderManagerTool(tmp_path)

    result = tool.run(
        {
            "device": {"serial": "ABC123"},
            "action": "unlock",
            "policy": {"allow_live_destructive_actions": False},
        }
    )

    assert result["status"] == "awaiting_policy_approval"
    assert result["unlock_issued"] is False
    assert result["blocks"] is True


def test_boot_validator_reads_boot_state(monkeypatch, tmp_path: Path) -> None:
    tool = BootValidatorTool(tmp_path)

    monkeypatch.setattr("app.tools.boot_validator.adb._adb_path", lambda: "/usr/bin/adb")

    responses = iter(
        [
            subprocess.CompletedProcess([], 0, stdout="green\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="1\n", stderr=""),
        ]
    )
    monkeypatch.setattr("app.tools.boot_validator.subprocess.run", lambda *args, **kwargs: next(responses))

    result = tool.run({"device": {"serial": "ABC123"}})

    assert result["status"] == "pass"
    assert result["blocks"] is False
    assert result["verified_boot_state"] == "green"
    assert result["bootloader_locked"] is True


def test_avb_signer_reports_missing_avbtool(monkeypatch, tmp_path: Path) -> None:
    tool = AVBSignerTool(tmp_path)
    monkeypatch.setattr("app.tools.avb_signer.shutil.which", lambda name: None)

    result = tool.run({"artifacts": ["boot.img"]})

    assert result["status"] == "avbtool_missing"
    assert result["blocks"] is False
    assert result["signed_artifacts"] == []


def test_source_resolver_no_longer_silent_stub(tmp_path: Path) -> None:
    tool = SourceResolverTool(tmp_path)

    result = tool.run({"strategy_id": "lineage"})

    assert result["status"] == "missing_research"
    assert result["blocks"] is True
    assert result["sources"] == []

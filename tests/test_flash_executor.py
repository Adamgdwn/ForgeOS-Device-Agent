import json
from pathlib import Path

from app.core.models import PolicyModel
from app.tools.flash_executor import FlashExecutorTool


def test_flash_executor_blocks_without_approval(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    session_dir.mkdir(parents=True)
    tool = FlashExecutorTool(tmp_path)
    manifest_path = session_dir / "runtime" / "build" / "artifact-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"status": "ready", "install_mode": "fastboot_images", "staged_files": [], "flash_steps": []}))

    result = tool.execute(
        {
            "session_dir": str(session_dir),
            "flash_plan": {
                "session_id": "sample",
                "build_path": "hardened_stock_path",
                "dry_run": True,
                "restore_path_available": True,
                "artifacts_ready": True,
                "install_mode": "fastboot_images",
                "artifact_manifest_path": str(manifest_path),
                "transport": "usb-adb",
                "steps": [],
                "status": "planned",
                "summary": "Prepared plan",
            },
            "approval": {
                "session_id": "sample",
                "approved": False,
            },
            "policy": PolicyModel().__dict__,
            "device": {"serial": "ABC123"},
        }
    )

    assert result["status"] == "awaiting_approval"


def test_flash_executor_completes_dry_run_when_approved(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    session_dir.mkdir(parents=True)
    tool = FlashExecutorTool(tmp_path)
    manifest_path = session_dir / "runtime" / "build" / "artifact-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    staged_image = session_dir / "runtime" / "build" / "staged" / "boot.img"
    staged_image.parent.mkdir(parents=True, exist_ok=True)
    staged_image.write_bytes(b"boot")
    manifest_path.write_text(
        json.dumps(
            {
                "status": "ready",
                "install_mode": "fastboot_images",
                "staged_files": [str(staged_image)],
                "flash_steps": [
                    {
                        "name": "flash_boot",
                        "kind": "flash",
                        "command": "fastboot flash boot boot.img",
                        "description": "Flash boot image.",
                    }
                ],
            }
        )
    )

    result = tool.execute(
        {
            "session_dir": str(session_dir),
            "flash_plan": {
                "session_id": "sample",
                "build_path": "hardened_stock_path",
                "dry_run": False,
                "restore_path_available": True,
                "artifacts_ready": True,
                "install_mode": "fastboot_images",
                "artifact_manifest_path": str(manifest_path),
                "transport": "usb-adb",
                "steps": [
                    {
                        "name": "flash_boot",
                        "kind": "flash",
                        "destructive": True,
                        "description": "Flash boot image.",
                        "command": "fastboot flash boot boot.img",
                    },
                    {
                        "name": "wipe_userdata",
                        "kind": "wipe",
                        "destructive": True,
                        "description": "Wipe user data.",
                    }
                ],
                "status": "planned",
                "summary": "Prepared plan",
            },
            "approval": {
                "session_id": "sample",
                "approved": True,
                "approval_scope": "full_wipe_and_rebuild",
                "confirmation_phrase": "WIPE_AND_REBUILD",
                "consequences_acknowledged": True,
                "restore_path_confirmed": True,
            },
            "policy": PolicyModel().__dict__,
            "device": {"serial": "ABC123"},
        },
        dry_run=True,
    )

    assert result["status"] == "dry_run_complete"
    assert result["details"]["dry_run"] is True


def test_flash_executor_runs_live_fastboot_steps(monkeypatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    session_dir.mkdir(parents=True)
    tool = FlashExecutorTool(tmp_path)
    manifest_path = session_dir / "runtime" / "build" / "artifact-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    staged_image = session_dir / "runtime" / "build" / "staged" / "boot.img"
    staged_image.parent.mkdir(parents=True, exist_ok=True)
    staged_image.write_bytes(b"boot")
    manifest_path.write_text(
        json.dumps(
            {
                "status": "ready",
                "install_mode": "fastboot_images",
                "staged_files": [str(staged_image)],
                "flash_steps": [
                    {
                        "name": "flash_boot",
                        "kind": "flash",
                        "command": "fastboot flash boot boot.img",
                        "description": "Flash boot image.",
                    }
                ],
            }
        )
    )
    calls: list[list[str]] = []

    def fake_run(args: list[str]) -> dict[str, object]:
        calls.append(args)
        return {"ok": True, "stdout": "ok", "stderr": "", "returncode": 0}

    monkeypatch.setattr("app.tools.flash_executor.fastboot.run", fake_run)

    result = tool.execute(
        {
            "session_dir": str(session_dir),
            "flash_plan": {
                "session_id": "sample",
                "build_path": "hardened_stock_path",
                "dry_run": False,
                "restore_path_available": True,
                "artifacts_ready": True,
                "install_mode": "fastboot_images",
                "artifact_manifest_path": str(manifest_path),
                "transport": "usb-fastboot",
                "steps": [
                    {
                        "name": "flash_boot",
                        "kind": "flash",
                        "destructive": True,
                        "description": "Flash boot image.",
                        "command": "fastboot flash boot boot.img",
                    },
                    {
                        "name": "boot_validation",
                        "kind": "validation",
                        "destructive": False,
                        "description": "Reboot after flashing.",
                        "command": "",
                    },
                ],
                "status": "planned",
                "summary": "Prepared plan",
            },
            "approval": {
                "session_id": "sample",
                "approved": True,
                "approval_scope": "full_wipe_and_rebuild",
                "confirmation_phrase": "WIPE_AND_REBUILD",
                "consequences_acknowledged": True,
                "restore_path_confirmed": True,
            },
            "policy": {**PolicyModel().__dict__, "allow_live_destructive_actions": True},
            "device": {"serial": "ABC123"},
        },
        dry_run=False,
    )

    assert result["status"] == "live_execution_complete"
    assert calls[0] == ["-s", "ABC123", "flash", "boot", str(staged_image)]

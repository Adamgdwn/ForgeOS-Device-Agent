from pathlib import Path

from app.core.models import PolicyModel
from app.tools.flash_executor import FlashExecutorTool


def test_flash_executor_blocks_without_approval(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    session_dir.mkdir(parents=True)
    tool = FlashExecutorTool(tmp_path)

    result = tool.execute(
        {
            "session_dir": str(session_dir),
            "flash_plan": {
                "session_id": "sample",
                "build_path": "hardened_stock_path",
                "dry_run": True,
                "restore_path_available": True,
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

    result = tool.execute(
        {
            "session_dir": str(session_dir),
            "flash_plan": {
                "session_id": "sample",
                "build_path": "hardened_stock_path",
                "dry_run": False,
                "restore_path_available": True,
                "transport": "usb-adb",
                "steps": [
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

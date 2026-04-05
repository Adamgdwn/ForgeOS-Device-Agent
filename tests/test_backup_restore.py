import json
from pathlib import Path

from app.core.bootstrap import run_bootstrap
from app.core.session_manager import SessionManager
from app.core.models import Transport
from app.tools.backup_restore import BackupAndRestorePlannerTool
from app.tools.restore_controller import RestoreControllerTool


def test_backup_restore_generates_bundle_and_restore_plan(tmp_path: Path) -> None:
    run_bootstrap(tmp_path)
    manager = SessionManager(tmp_path)
    session_dir = manager.create_or_resume(
        {
            "manufacturer": "Samsung",
            "model": "Galaxy A5",
            "serial": "usb-1234",
            "transport": Transport.USB_MTP,
        }
    )
    backup_tool = BackupAndRestorePlannerTool(tmp_path)
    restore_tool = RestoreControllerTool(tmp_path)

    backup = backup_tool.execute(
        {
            "device": {
                "manufacturer": "Samsung",
                "model": "Galaxy A5",
                "serial": "usb-1234",
                "transport": Transport.USB_MTP,
            },
            "session_dir": str(session_dir),
            "assessment": {"restore_path_feasible": False},
        }
    )

    assert Path(backup["plan"]["backup_bundle_path"]).exists()
    assert Path(backup["plan"]["metadata_backup_path"]).exists()

    restore = restore_tool.execute(
        {
            "session_dir": str(session_dir),
            "backup_plan": backup["plan"],
        }
    )
    restore_plan_path = Path(restore["restore_plan_path"])
    assert restore_plan_path.exists()
    details = json.loads(restore_plan_path.read_text())
    assert details["status"] == "planned"

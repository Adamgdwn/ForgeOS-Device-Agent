from pathlib import Path

from app.core.models import Transport
from app.tools.autonomous_engagement import AutonomousEngagementTool


def test_autonomous_engagement_reports_usb_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.integrations.adb.start_server", lambda: {"ok": True})
    monkeypatch.setattr("app.integrations.adb.reconnect", lambda: {"ok": True})
    monkeypatch.setattr("app.integrations.adb.raw_devices", lambda: [])
    monkeypatch.setattr(
        "app.integrations.udev.list_usb_mobile_devices",
        lambda: [{"description": "Samsung MTP", "vendor_hint": "Samsung"}],
    )

    tool = AutonomousEngagementTool(tmp_path)
    result = tool.execute(
        {
            "device": {
                "transport": Transport.USB_MTP.value,
            },
            "session_dir": str(tmp_path),
        }
    )

    assert result["engagement_status"] == "usb_only_detected"
    assert "safe adb engagement" in result["summary"]

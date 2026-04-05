from pathlib import Path

from app.tools.strategy_selector import BuildStrategySelectorTool


def test_strategy_selector_prefers_senior_friendly_path(tmp_path: Path) -> None:
    tool = BuildStrategySelectorTool(tmp_path)
    result = tool.execute(
        {
            "assessment": {"support_status": "actionable", "recommended_path": "hardened_existing_os"},
            "device": {"transport": "usb-adb"},
            "user_profile": {
                "persona": "senior",
                "technical_comfort": "low",
                "primary_priority": "simplicity",
                "google_services_preference": "keep_google",
            },
            "os_goals": {
                "top_goal": "simplicity",
                "secondary_goal": "security",
                "requires_reliable_updates": True,
                "prefers_long_battery_life": True,
                "prefers_lockdown_defaults": True,
            },
        }
    )
    assert result["strategy_id"] == "hardened_stock"


def test_strategy_selector_prefers_privacy_path(tmp_path: Path) -> None:
    tool = BuildStrategySelectorTool(tmp_path)
    result = tool.execute(
        {
            "assessment": {"support_status": "actionable", "recommended_path": "hardened_existing_os"},
            "device": {"transport": "usb-adb"},
            "user_profile": {
                "persona": "privacy_focused",
                "technical_comfort": "medium",
                "primary_priority": "privacy",
                "google_services_preference": "remove_google",
            },
            "os_goals": {
                "top_goal": "privacy",
                "secondary_goal": "security",
                "requires_reliable_updates": True,
                "prefers_long_battery_life": True,
                "prefers_lockdown_defaults": True,
            },
        }
    )
    assert result["strategy_id"] == "privacy_hardened_aftermarket"

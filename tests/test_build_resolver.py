from pathlib import Path

from app.tools.build_resolver import BuildResolverTool


def test_build_resolver_returns_research_only_for_transport_recovery(tmp_path: Path) -> None:
    tool = BuildResolverTool(tmp_path)
    result = tool.execute(
        {
            "assessment": {"support_status": "research_only"},
            "connection_plan": {},
            "selected_strategy": "transport_recovery",
            "user_profile": {},
            "os_goals": {},
        }
    )
    assert result["os_path"] == "research_only_path"


def test_build_resolver_returns_aftermarket_path(tmp_path: Path) -> None:
    tool = BuildResolverTool(tmp_path)
    result = tool.execute(
        {
            "assessment": {"support_status": "actionable"},
            "connection_plan": {},
            "selected_strategy": "aftermarket_rom",
            "user_profile": {"lawful_use_attested": True},
            "os_goals": {},
        }
    )
    assert result["os_path"] == "aftermarket_path"


def test_build_resolver_uses_operator_review_feature_decisions(tmp_path: Path) -> None:
    tool = BuildResolverTool(tmp_path)
    result = tool.execute(
        {
            "assessment": {"support_status": "actionable"},
            "connection_plan": {},
            "selected_strategy": "hardened_stock",
            "user_profile": {
                "google_services_preference": "remove_google",
                "target_use_case": "lightweight_custom_android",
                "lawful_use_attested": True,
            },
            "os_goals": {"requires_reliable_updates": True, "prefers_long_battery_life": True, "prefers_lockdown_defaults": True},
            "recommendation": {
                "recommended_use_case": "lightweight_custom_android",
                "options": [{"option_id": "lightweight_custom_android", "label": "Lightweight custom Android"}],
            },
            "operator_review": {
                "selected_option_id": "lightweight_custom_android",
                "accepted_feature_ids": ["debloated_apps", "lockdown_defaults"],
                "rejected_feature_ids": ["google_services"],
            },
        }
    )
    assert result["selected_option_id"] == "lightweight_custom_android"
    assert result["proposed_os_name"].startswith("Hardened stock Android")
    assert result["included_feature_ids"] == ["debloated_apps", "lockdown_defaults"]
    assert "wipe_autostart" in result["rejected_feature_ids"]
    assert "proposal-manifest" in result["artifact_requirements"]


def test_build_resolver_stays_research_only_without_lawful_attestation(tmp_path: Path) -> None:
    tool = BuildResolverTool(tmp_path)
    result = tool.execute(
        {
            "assessment": {"support_status": "actionable"},
            "connection_plan": {"recommended_adapter": {"adapter_id": "adb"}},
            "selected_strategy": "aftermarket_rom",
            "user_profile": {
                "target_use_case": "home_control_panel",
                "desired_end_product": "Wall mounted Home Assistant dashboard",
                "lawful_use_attested": False,
            },
            "os_goals": {},
            "recommendation": {"recommended_use_case": "home_control_panel", "options": []},
            "operator_review": {},
        }
    )

    assert result["os_path"] == "research_only_path"
    assert "lawful authorization" in result["reason"]
    assert "end_product_brief" in result["included_feature_ids"]
    assert "lock_bypass" in result["rejected_feature_ids"]

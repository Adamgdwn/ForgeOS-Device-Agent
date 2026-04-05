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
            "user_profile": {},
            "os_goals": {},
        }
    )
    assert result["os_path"] == "aftermarket_path"

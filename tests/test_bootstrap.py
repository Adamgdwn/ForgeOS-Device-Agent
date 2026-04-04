from pathlib import Path

from app.core.bootstrap import run_bootstrap


def test_bootstrap_creates_workspace_and_master(tmp_path: Path) -> None:
    details = run_bootstrap(tmp_path)

    assert (tmp_path / "forgeos.code-workspace").exists()
    assert (tmp_path / "master" / "policies" / "default_policy.json").exists()
    assert (tmp_path / "output").exists()
    assert Path(details["bootstrap_report"]).exists()

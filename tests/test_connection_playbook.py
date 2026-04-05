from pathlib import Path

from app.core.connection_playbook import ConnectionPlaybookEngine


def test_connection_playbook_prefers_exact_model(tmp_path: Path) -> None:
    playbook_dir = tmp_path / "master" / "playbooks" / "connection"
    playbook_dir.mkdir(parents=True)
    (playbook_dir / "generic-android.json").write_text(
        '{"playbook_id":"generic-android","states":{"usb_only":{"title":"Generic","steps":["generic"]}}}'
    )
    (playbook_dir / "samsung-galaxy-a5.json").write_text(
        '{"playbook_id":"samsung-galaxy-a5","states":{"usb_only":{"title":"Galaxy A5","steps":["specific"]}}}'
    )

    engine = ConnectionPlaybookEngine(tmp_path)
    result = engine.resolve("Samsung", "Galaxy A5", "usb_only_detected", "usb-mtp")

    assert result["playbook_id"] == "samsung-galaxy-a5"
    assert result["title"] == "Galaxy A5"


def test_connection_playbook_falls_back_to_generic(tmp_path: Path) -> None:
    playbook_dir = tmp_path / "master" / "playbooks" / "connection"
    playbook_dir.mkdir(parents=True)
    (playbook_dir / "generic-android.json").write_text(
        '{"playbook_id":"generic-android","states":{"default":{"title":"Generic default","steps":["generic"]}}}'
    )

    engine = ConnectionPlaybookEngine(tmp_path)
    result = engine.resolve("Unknown", "Unknown", "unknown", "unknown")

    assert result["playbook_id"] == "generic-android"
    assert result["title"] == "Generic default"

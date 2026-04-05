import json
import tarfile
from pathlib import Path

from app.tools.image_builder import ImageBuilderTool


def test_image_builder_stages_fastboot_images(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    source_dir = session_dir / "artifacts" / "os-source"
    source_dir.mkdir(parents=True)
    (source_dir / "boot.img").write_bytes(b"boot")
    (source_dir / "system.img").write_bytes(b"system")

    result = ImageBuilderTool(tmp_path).execute(
        {
            "session_dir": str(session_dir),
            "build_plan": {
                "os_path": "maintainable_hardened_path",
                "proposed_os_name": "Hardened stock Android for Accessibility Focused Phone",
            },
            "device": {"serial": "ABC123"},
        }
    )

    assert result["status"] == "ready"
    manifest_path = session_dir / "runtime" / "build" / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["install_mode"] == "fastboot_images"
    assert len(manifest["flash_steps"]) == 2
    bundle_path = session_dir / "runtime" / "build" / "flashable-artifacts.tar.gz"
    assert bundle_path.exists()
    with tarfile.open(bundle_path, "r:gz") as bundle:
        names = bundle.getnames()
    assert "boot.img" in names
    assert "system.img" in names


def test_image_builder_records_missing_source_requirements(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    session_dir.mkdir(parents=True)

    result = ImageBuilderTool(tmp_path).execute(
        {
            "session_dir": str(session_dir),
            "build_plan": {"os_path": "maintainable_hardened_path"},
            "device": {"serial": "ABC123"},
        }
    )

    assert result["status"] == "missing_source"
    manifest_path = session_dir / "runtime" / "build" / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["missing_requirements"]

from __future__ import annotations

import json
from pathlib import Path

from app.tools.source_builder import SourceBuilderTool


def test_source_builder_writes_source_build_plan(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "demo"
    session_dir.mkdir(parents=True)

    result = SourceBuilderTool(tmp_path).execute(
        {
            "session_dir": str(session_dir),
            "device": {"manufacturer": "Example", "model": "Old Tablet", "device_codename": "oldtab"},
            "build_plan": {"os_path": "maintainable_hardened_path"},
            "policy": {"allow_long_source_builds": False, "max_source_build_seconds": 1},
            "research": {"lineageos_supported": True},
        }
    )

    plan_path = session_dir / "runtime" / "build-from-source" / "source-build-plan.json"
    request_path = session_dir / "runtime" / "build-from-source" / "source-build-request.json"
    script_path = session_dir / "runtime" / "build-from-source" / "build_source_artifacts.sh"
    plan = json.loads(plan_path.read_text())
    request = json.loads(request_path.read_text())

    assert result["status"] == "build_plan_ready"
    assert plan["strategy"]["id"] == "lineageos_source_build"
    assert request["recommended_builder"] == "lineageos_source_build"
    assert script_path.exists()


def test_source_builder_runs_configured_local_build(tmp_path: Path, monkeypatch) -> None:
    session_dir = tmp_path / "devices" / "demo"
    session_dir.mkdir(parents=True)
    build_script = tmp_path / "fake_android_build.sh"
    build_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "python3 - <<'PY'\n"
        "import os\n"
        "from pathlib import Path\n"
        "Path(os.environ['FORGEOS_SOURCE_OUTPUT_DIR'], 'built-system.img').write_bytes(b'x' * (11 * 1024 * 1024))\n"
        "PY\n"
    )
    build_script.chmod(0o755)
    monkeypatch.setenv("FORGEOS_ANDROID_BUILD_COMMAND", str(build_script))

    result = SourceBuilderTool(tmp_path).execute(
        {
            "session_dir": str(session_dir),
            "device": {"manufacturer": "Example", "model": "Old Tablet", "device_codename": "oldtab"},
            "build_plan": {"os_path": "maintainable_hardened_path"},
            "policy": {"allow_long_source_builds": True, "max_source_build_seconds": 10},
            "research": {},
        },
        dry_run=False,
    )

    transcript_path = session_dir / "runtime" / "build-from-source" / "build-transcript.json"
    assert result["status"] == "ready"
    assert Path(result["details"]["staged_files"][0]).name == "built-system.img"
    assert transcript_path.exists()

import json
import zipfile
from pathlib import Path

from app.core.codegen_runtime import CodegenRuntime


def test_codegen_runtime_generates_and_executes_remediation_artifact(monkeypatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    (session_dir / "codegen").mkdir(parents=True, exist_ok=True)
    runtime = CodegenRuntime(tmp_path)

    generated = runtime.generate(
        session_dir,
        blocker={
            "blocker_type": "transport_blocker",
            "planned_next_action": "generate_transport_triage",
        },
        connection_plan={"recommended_adapter": {"adapter_id": "mtp-bridge"}},
        build_plan={"os_path": "research_only_path"},
    )

    monkeypatch.setenv(
        "FORGEOS_TEST_REMEDIATION_RESULT",
        json.dumps(
            {
                "status": "solved",
                "summary": "Synthetic remediation solved the transport blocker.",
                "profile_updates": {"transport": "usb-adb", "manufacturer": "Samsung", "model": "SM-A520W"},
            }
        ),
    )
    executed = runtime.execute_generated(session_dir, generated)
    inspected = runtime.inspect_result(executed)

    assert generated["task"]["task_id"] == "host-transport-triage"
    assert generated["task"]["remediation_family"] == "host_transport_triage"
    assert executed["status"] == "executed"
    assert inspected["status"] == "solved"
    assert inspected["profile_updates"]["transport"] == "usb-adb"


def test_codegen_runtime_source_acquisition_stages_local_firmware(monkeypatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(downloads_dir / "SM-A520W_update.zip", "w") as archive:
        archive.writestr("payload.bin", b"\0" * (1024 * 1024 + 1))
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime = CodegenRuntime(Path(__file__).resolve().parents[1])

    generated = runtime.generate(
        session_dir,
        blocker={
            "blocker_type": "source_blocker",
            "planned_next_action": "source_acquisition_and_staging",
            "summary": "Samsung SM-A520W (a5y17ltecan) is connected and ready, but no OS source artifacts are staged.",
        },
        connection_plan={"recommended_adapter": {"adapter_id": "adb"}},
        build_plan={"os_path": "maintainable_hardened_path"},
    )

    executed = runtime.execute_generated(session_dir, generated)
    inspected = runtime.inspect_result(executed)
    staged_path = session_dir / "artifacts" / "os-source" / "SM-A520W_update.zip"

    assert generated["task"]["task_id"] == "source-acquisition-and-staging"
    assert generated["task"]["remediation_family"] == "source_acquisition_and_staging"
    assert executed["status"] == "executed"
    assert inspected["status"] == "solved"
    assert staged_path.exists()
    assert inspected["evidence"]["source_acquisition"]["staged_files"] == [str(staged_path)]


def test_codegen_runtime_source_acquisition_reports_partial_when_nothing_is_staged(tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    runtime = CodegenRuntime(Path(__file__).resolve().parents[1])

    generated = runtime.generate(
        session_dir,
        blocker={
            "blocker_type": "source_blocker",
            "planned_next_action": "source_acquisition_and_staging",
            "summary": "Samsung SM-A520W (a5y17ltecan) is connected and ready, but no OS source artifacts are staged.",
        },
        connection_plan={"recommended_adapter": {"adapter_id": "adb"}},
        build_plan={"os_path": "maintainable_hardened_path"},
    )

    executed = runtime.execute_generated(session_dir, generated)
    inspected = runtime.inspect_result(executed)

    assert executed["status"] == "executed"
    assert inspected["status"] == "partial"
    assert inspected["evidence"]["source_acquisition"]["staged_files"] == []


def test_codegen_runtime_removes_mock_source_artifacts(monkeypatch, tmp_path: Path) -> None:
    session_dir = tmp_path / "devices" / "sample"
    runtime = CodegenRuntime(Path(__file__).resolve().parents[1])
    generated = {
        "task": {"remediation_family": "source_acquisition_and_staging"},
        "script_path": str(session_dir / "codegen" / "mock_writer.py"),
    }
    script_path = Path(generated["script_path"])
    script_path.parent.mkdir(parents=True)
    script_path.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "source_dir = Path(__file__).parents[1] / 'artifacts' / 'os-source'",
                "source_dir.mkdir(parents=True, exist_ok=True)",
                "(source_dir / 'boot.img').write_text('Mock content for boot.img')",
                "print('{\"status\":\"solved\",\"summary\":\"staged\"}')",
            ]
        )
    )

    executed = runtime.execute_generated(session_dir, generated)
    inspected = runtime.inspect_result(executed)

    assert inspected["status"] == "partial"
    assert not (session_dir / "artifacts" / "os-source" / "boot.img").exists()
    assert inspected["evidence"]["source_acquisition"]["staged_files"] == []
    assert inspected["evidence"]["source_acquisition"]["invalid_artifacts_removed"]

import json
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

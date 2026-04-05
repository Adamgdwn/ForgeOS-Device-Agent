from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.core.models import utc_now


class CodegenRuntime:
    def __init__(self, root: Path) -> None:
        self.root = root

    def generate(
        self,
        session_dir: Path,
        blocker: dict[str, Any],
        connection_plan: dict[str, Any],
        build_plan: dict[str, Any],
    ) -> dict[str, Any]:
        runtime_dir = session_dir / "codegen"
        runtime_dir.mkdir(parents=True, exist_ok=True)

        task = self._task_manifest(blocker, connection_plan, build_plan)
        task_path = runtime_dir / "remediation-task.json"
        task_path.write_text(json.dumps(task, indent=2))

        artifact_name = f"generated_{task['task_id'].replace('-', '_')}.py"
        script_path = runtime_dir / artifact_name
        script_path.write_text(self._artifact_source(task, session_dir))

        queue = {
            "generated_at": utc_now(),
            "objective": "Generate and run a remediation artifact that helps ForgeOS continue autonomously.",
            "task": task,
            "files_generated": [str(script_path), str(task_path)],
            "next_execution_step": f"Execute {script_path.name} and inspect its remediation result.",
        }
        queue_path = runtime_dir / "execution-queue.json"
        queue_path.write_text(json.dumps(queue, indent=2))
        return {
            "task": task,
            "generated_files": [str(script_path), str(task_path), str(queue_path)],
            "summary": f"Generated remediation artifact `{artifact_name}` for blocker `{blocker.get('blocker_type')}`.",
            "queue_path": str(queue_path),
            "script_path": str(script_path),
            "task_path": str(task_path),
        }

    def execute_generated(self, session_dir: Path, generated: dict[str, Any]) -> dict[str, Any]:
        script_path = Path(str(generated["script_path"]))
        transcripts_dir = session_dir / "execution"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts_dir / "artifact-execution.json"
        interpreter = self.root / ".venv" / "bin" / "python"
        command = [str(interpreter if interpreter.exists() else "python3"), str(script_path)]
        completed = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
        output = completed.stdout.strip()
        parsed: dict[str, Any]
        try:
            parsed = json.loads(output) if output else {}
        except json.JSONDecodeError:
            parsed = {"status": "artifact_failed", "summary": "Generated artifact emitted non-JSON output.", "raw_stdout": output}
        result = {
            "generated_at": utc_now(),
            "command": command,
            "returncode": completed.returncode,
            "stdout": output,
            "stderr": completed.stderr.strip(),
            "result": parsed,
        }
        transcript_path.write_text(json.dumps(result, indent=2))
        return {
            "status": "executed" if completed.returncode == 0 else "artifact_failed",
            "summary": parsed.get("summary", "Executed remediation artifact."),
            "transcript_path": str(transcript_path),
            "result": parsed,
            "returncode": completed.returncode,
        }

    def inspect_result(self, execution_result: dict[str, Any]) -> dict[str, Any]:
        parsed = execution_result.get("result", {})
        status = parsed.get("status", "artifact_failed")
        return {
            "status": status,
            "summary": parsed.get("summary", "No remediation summary available."),
            "profile_updates": parsed.get("profile_updates", {}),
            "engagement_updates": parsed.get("engagement_updates", {}),
            "assessment_updates": parsed.get("assessment_updates", {}),
            "evidence": parsed.get("evidence", {}),
            "next_action": parsed.get("next_action", "reclassify"),
        }

    def _task_manifest(
        self,
        blocker: dict[str, Any],
        connection_plan: dict[str, Any],
        build_plan: dict[str, Any],
    ) -> dict[str, Any]:
        blocker_type = blocker.get("blocker_type", "none")
        recommended_adapter = (connection_plan.get("recommended_adapter") or {}).get("adapter_id", "observe")
        task_id = f"{blocker_type}-remediation"
        objective = "Collect richer host/device evidence and attempt the next software-solvable continuation step."
        remediation_family = "generic_diagnostic"
        if blocker_type == "transport_blocker":
            task_id = "host-transport-triage"
            remediation_family = "host_transport_triage"
            objective = "Probe adb, fastboot, USB descriptors, and host permissions again and upgrade the session if a managed transport exists."
        elif blocker_type == "source_blocker":
            task_id = "generic-adapter-scaffold"
            remediation_family = "generic_adapter_scaffold"
            objective = "Generate a session-local generic adapter scaffold and produce executable evidence for the next path."
        elif blocker_type == "subsystem_blocker":
            task_id = "followup-diagnostic"
            remediation_family = "followup_diagnostic"
            objective = "Generate a follow-up generic diagnostic after a previous remediation artifact failed to improve the session."
        return {
            "task_id": task_id,
            "blocker_type": blocker_type,
            "recommended_adapter": recommended_adapter,
            "remediation_family": remediation_family,
            "objective": objective,
            "build_path": build_plan.get("os_path", "unknown"),
            "generated_at": utc_now(),
        }

    def _artifact_source(self, task: dict[str, Any], session_dir: Path) -> str:
        session_dir_str = str(session_dir)
        root_str = str(self.root)
        remediation_family = task.get("remediation_family", "generic_diagnostic")
        return f"""from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"{root_str}")
SESSION_DIR = Path(r"{session_dir_str}")
REMEDIATION_FAMILY = {json.dumps(remediation_family)}
injected = os.environ.get("FORGEOS_TEST_REMEDIATION_RESULT")
if injected:
    print(injected)
    raise SystemExit(0)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.integrations import adb, fastboot, fastbootd  # noqa: E402
from app.integrations.udev import list_usb_mobile_devices  # noqa: E402


def _safe_run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {{
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }}


def _write_json(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return str(path)


def _sysfs_usb_snapshot() -> list[dict[str, str]]:
    snapshot: list[dict[str, str]] = []
    base = Path("/sys/bus/usb/devices")
    if not base.exists():
        return snapshot
    for entry in base.iterdir():
        vendor = entry / "idVendor"
        product = entry / "idProduct"
        if not vendor.exists() or not product.exists():
            continue
        record = {{
            "path": str(entry),
            "vendor_id": vendor.read_text().strip(),
            "product_id": product.read_text().strip(),
        }}
        for optional in ["manufacturer", "product", "serial"]:
            optional_path = entry / optional
            if optional_path.exists():
                record[optional] = optional_path.read_text().strip()
        snapshot.append(record)
    return snapshot


def _adb_partition_probe(serial: str) -> dict[str, object]:
    keys = [
        "ro.boot.slot_suffix",
        "ro.boot.dynamic_partitions",
        "ro.build.ab_update",
        "ro.product.cpu.abi",
        "ro.board.platform",
        "ro.hardware",
        "ro.build.fingerprint",
    ]
    getprops = {{}}
    for key in keys:
        getprops[key] = adb.getprop(serial, key)
    by_name = adb.shell(serial, ["sh", "-c", "ls -1 /dev/block/by-name 2>/dev/null | head -n 128"])
    mounts = adb.shell(serial, ["sh", "-c", "cat /proc/mounts | head -n 64"])
    return {{
        "getprops": getprops,
        "block_by_name": by_name.get("stdout", "").splitlines() if by_name.get("ok") else [],
        "mounts": mounts.get("stdout", "").splitlines() if mounts.get("ok") else [],
    }}


def _fastboot_probe() -> dict[str, object]:
    devices = fastboot.list_devices()
    first_serial = devices[0]["serial"] if devices else None
    variables = fastboot.getvar_all(first_serial) if first_serial else {{"ok": False, "reason": "no fastboot device"}}
    return {{
        "devices": devices,
        "getvar_all": variables,
    }}


def _build_resolver_candidates(evidence: dict[str, object]) -> dict[str, object]:
    adb_devices = evidence.get("adb_devices", [])
    fastboot_probe = evidence.get("fastboot_probe", {{}})
    partition_probe = evidence.get("partition_probe", {{}})
    candidates = []
    if adb_devices:
        candidates.append({{
            "id": "maintainable_hardened_path",
            "confidence": 0.72,
            "reason": "adb transport is available, so the runtime can continue generic non-destructive interrogation safely.",
        }})
    if partition_probe.get("getprops", {{}}).get("ro.boot.dynamic_partitions") == "true":
        candidates.append({{
            "id": "gsi_candidate_path",
            "confidence": 0.48,
            "reason": "Dynamic partitions are present, so a generic system image branch may be worth evaluating later.",
        }})
    if fastboot_probe.get("devices"):
        candidates.append({{
            "id": "low_level_flash_candidate",
            "confidence": 0.61,
            "reason": "fastboot transport is present, allowing low-level metadata and flash planning.",
        }})
    if not candidates:
        candidates.append({{
            "id": "transport_recovery",
            "confidence": 0.55,
            "reason": "Transport still needs improvement before a stronger build path can be selected.",
        }})
    return {{
        "generated_by": "generic_remediation_runtime",
        "candidates": candidates,
    }}


def _write_generic_adapter_scaffold() -> str:
    scaffold_path = SESSION_DIR / "connection" / "generated_generic_adapter.py"
    scaffold = '''from __future__ import annotations

def run() -> dict[str, object]:
    return {{
        "status": "scaffold",
        "summary": "Generic adapter scaffold generated for this session.",
    }}
'''
    scaffold_path.parent.mkdir(parents=True, exist_ok=True)
    scaffold_path.write_text(scaffold)
    return str(scaffold_path)


def main() -> None:
    adb_devices = adb.list_devices()
    raw_adb = adb.raw_devices()
    fastboot_devices = fastboot.list_devices()
    fastbootd_devices = fastbootd.list_devices()
    usb_devices = list_usb_mobile_devices()
    usb_sysfs = _sysfs_usb_snapshot()
    host_diagnostics = {{
        "lsusb": _safe_run(["lsusb"]),
        "adb_devices": _safe_run([adb._adb_path(), "devices", "-l"]) if adb.adb_available() else {{"returncode": 1, "stdout": "", "stderr": "adb unavailable"}},
        "fastboot_devices": _safe_run([fastboot._fastboot_path(), "devices"]) if fastboot.fastboot_available() else {{"returncode": 1, "stdout": "", "stderr": "fastboot unavailable"}},
    }}
    fastboot_probe = _fastboot_probe()
    partition_probe = _adb_partition_probe(adb_devices[0]["serial"]) if adb_devices else {{}}
    evidence = {{
        "adb_devices": adb_devices,
        "raw_adb": raw_adb,
        "fastboot_devices": fastboot_devices,
        "fastbootd_devices": fastbootd_devices,
        "usb_devices": usb_devices,
        "usb_sysfs": usb_sysfs,
        "host_diagnostics": host_diagnostics,
        "fastboot_probe": fastboot_probe,
        "partition_probe": partition_probe,
    }}
    diagnostics_path = _write_json(SESSION_DIR / "raw" / "host-transport-diagnostics.json", evidence)
    partition_probe_path = _write_json(SESSION_DIR / "raw" / "partition-probe.json", partition_probe if isinstance(partition_probe, dict) else {{}})
    candidates = _build_resolver_candidates(evidence)
    build_candidates_path = _write_json(SESSION_DIR / "plans" / "build-resolver-candidates.json", candidates)

    if REMEDIATION_FAMILY == "generic_adapter_scaffold":
        scaffold_path = _write_generic_adapter_scaffold()
        result = {{
            "status": "solved",
            "summary": "Generated a generic adapter scaffold and build-path candidates for continued autonomous work.",
            "evidence": {{
                **evidence,
                "diagnostics_path": diagnostics_path,
                "partition_probe_path": partition_probe_path,
                "build_candidates_path": build_candidates_path,
                "scaffold_path": scaffold_path,
            }},
            "next_action": "reclassify",
        }}
        print(json.dumps(result))
        return

    if adb_devices:
        serial = adb_devices[0]["serial"]
        profile = adb.describe_device(serial)
        result = {{
            "status": "solved",
            "summary": "Generated host transport triage confirmed adb visibility and upgraded the session transport.",
            "profile_updates": profile,
            "engagement_updates": {{
                "engagement_status": "adb_connected",
                "summary": "ForgeOS confirmed adb transport from a generated remediation artifact.",
            }},
            "assessment_updates": {{
                "support_status": "actionable",
                "restore_path_feasible": True,
                "recommended_path": "hardened_existing_os",
            }},
            "evidence": {{
                **evidence,
                "diagnostics_path": diagnostics_path,
                "partition_probe_path": partition_probe_path,
                "build_candidates_path": build_candidates_path,
            }},
            "next_action": "reclassify",
        }}
        print(json.dumps(result))
        return

    if any(entry.get("status") == "unauthorized" for entry in raw_adb):
        result = {{
            "status": "needs_user_action",
            "summary": "Generated transport triage reached adb visibility but the phone still requires trust approval.",
            "engagement_updates": {{
                "engagement_status": "awaiting_user_approval",
                "summary": "ForgeOS confirmed adb visibility and is waiting for USB trust approval.",
                "next_steps": [
                    "Unlock the phone.",
                    "Approve the USB debugging trust prompt.",
                ],
            }},
            "evidence": {{
                **evidence,
                "diagnostics_path": diagnostics_path,
                "partition_probe_path": partition_probe_path,
                "build_candidates_path": build_candidates_path,
            }},
            "next_action": "question_gate",
        }}
        print(json.dumps(result))
        return

    result = {{
        "status": "needs_user_action",
        "summary": "Generated host transport triage did not find a manageable transport beyond current USB visibility.",
        "evidence": {{
            **evidence,
            "diagnostics_path": diagnostics_path,
            "partition_probe_path": partition_probe_path,
            "build_candidates_path": build_candidates_path,
        }},
        "next_action": "question_gate",
    }}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
"""

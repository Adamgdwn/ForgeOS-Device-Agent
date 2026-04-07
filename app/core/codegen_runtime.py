from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from app.core.models import utc_now


def _slug(value: str | None) -> str:
    if not value:
        return "unknown"
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_") or "unknown"


def _source_hints_for(manufacturer: str, model: str, codename: str) -> list[str]:
    m = manufacturer.lower()
    hints: list[str] = []
    if "samsung" in m:
        hints += [
            f"Samsung stock firmware: SamFirm / SamLoader / Frija — search for {model}",
            "LineageOS unofficial or official builds may exist for this model",
            "Check XDA Developers for {model} / {codename} threads",
        ]
    elif "google" in m or "pixel" in m:
        hints += [
            f"Google factory images: developers.google.com/android/images — search for {codename}",
            "GrapheneOS (Pixel devices): grapheneos.org/install",
            "CalyxOS: calyxos.org/install/devices",
        ]
    elif "motorola" in m or "lenovo" in m:
        hints += [
            f"Motorola stock firmware repository — search for {model} / {codename}",
            "LineageOS may have official or unofficial support for this model",
        ]
    elif "oneplus" in m:
        hints += [
            f"OnePlus official firmware: oneplus.com/support/manuals — search {model}",
            "OxygenOS and LineageOS images available for most OnePlus devices",
        ]
    elif "xiaomi" in m or "redmi" in m or "poco" in m:
        hints += [
            f"Xiaomi firmware: miuirom.org or firmware.mobi — search {codename}",
            "MIUI or HyperOS firmware updater tool available for Windows",
        ]
    elif "fairphone" in m:
        hints += [
            "Fairphone open-source OS (FPOS) and /e/OS available — see fairphone.com",
        ]
    elif "nothing" in m:
        hints += [
            f"Nothing OS firmware — check nothing.community for {model} software threads",
        ]
    else:
        hints += [
            f"Search firmware repositories for {manufacturer} {model} ({codename})",
            "Check XDA Developers for device-specific threads",
            "LineageOS may have support: lineageos.org/devices",
        ]
    return hints


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

    def generate_device_adapter(
        self,
        session_dir: Path,
        device_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a device-specific OEM adapter for a device that has no master adapter.

        Writes `devices/<session>/adapters/<key>.py` — a runnable + importable module
        that can probe the device, describe flash commands, and run a self-test.
        Also builds the matching connection playbook JSON.

        Returns a dict with: adapter_key, adapter_path, playbook, playbook_path.
        """
        manufacturer = str(device_context.get("manufacturer") or "Unknown")
        model = str(device_context.get("model") or "Unknown")
        codename = str(device_context.get("device_codename") or "")
        transport = str(device_context.get("transport") or "usb-unknown")
        android_version = str(device_context.get("android_version") or "")
        bootloader_locked = device_context.get("bootloader_locked")
        serial = str(device_context.get("serial") or "")

        hw = dict(device_context.get("hardware_snapshot") or {})
        board = str(hw.get("board") or hw.get("hardware") or "")
        abi = str(hw.get("cpu_abi") or "arm64-v8a")
        slot_suffix = str(hw.get("slot_suffix") or device_context.get("slot_info", {}).get("slot_suffix") or "")
        ab_slots = slot_suffix in {"_a", "_b", "a", "b"}

        key = f"{_slug(manufacturer)}_{_slug(model)}"
        adapter_dir = session_dir / "adapters"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        adapter_path = adapter_dir / f"{key}.py"
        adapter_path.write_text(
            self._device_adapter_source(
                key=key,
                manufacturer=manufacturer,
                model=model,
                codename=codename,
                transport=transport,
                android_version=android_version,
                bootloader_locked=bootloader_locked,
                ab_slots=ab_slots,
                board=board,
                abi=abi,
            )
        )
        playbook = self._device_adapter_playbook(
            key=key,
            manufacturer=manufacturer,
            model=model,
            codename=codename,
            transport=transport,
        )
        playbook_path = adapter_dir / f"{key}.json"
        playbook_path.write_text(json.dumps(playbook, indent=2))
        return {
            "adapter_key": key,
            "adapter_path": str(adapter_path),
            "playbook": playbook,
            "playbook_path": str(playbook_path),
            "summary": f"Generated device-specific adapter `{key}` for {manufacturer} {model}.",
        }

    def execute_adapter_self_test(
        self,
        session_dir: Path,
        adapter_path: str,
    ) -> dict[str, Any]:
        """Run a generated adapter's self_test() and return structured result."""
        transcripts_dir = session_dir / "adapters"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcripts_dir / "self-test-result.json"
        interpreter = self.root / ".venv" / "bin" / "python"
        command = [str(interpreter if interpreter.exists() else "python3"), adapter_path]
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
            parsed = {"status": "adapter_failed", "summary": "Adapter self-test emitted non-JSON.", "raw_stdout": output}
        result = {
            "generated_at": utc_now(),
            "command": command,
            "returncode": completed.returncode,
            "stdout": output,
            "stderr": completed.stderr.strip(),
            "result": parsed,
        }
        transcript_path.write_text(json.dumps(result, indent=2))
        test_passed = completed.returncode == 0 and parsed.get("status") in {
            "probe_pass", "probe_no_device"
        }
        return {
            "status": "pass" if test_passed else "fail",
            "adapter_key": parsed.get("adapter_key", ""),
            "summary": parsed.get("summary", "Adapter self-test ran."),
            "probe_result": parsed.get("probe", {}),
            "transcript_path": str(transcript_path),
            "result": parsed,
            "returncode": completed.returncode,
        }

    @staticmethod
    def _device_adapter_source(
        *,
        key: str,
        manufacturer: str,
        model: str,
        codename: str,
        transport: str,
        android_version: str,
        bootloader_locked: bool | None,
        ab_slots: bool,
        board: str,
        abi: str,
    ) -> str:
        bl = "True" if bootloader_locked else ("False" if bootloader_locked is False else "None")
        return f'''from __future__ import annotations

import json
import sys
from pathlib import Path

# Device constants captured at first detection
ADAPTER_KEY = {json.dumps(key)}
MANUFACTURER = {json.dumps(manufacturer)}
MODEL = {json.dumps(model)}
CODENAME = {json.dumps(codename)}
ANDROID_VERSION = {json.dumps(android_version)}
TRANSPORT = {json.dumps(transport)}
BOOTLOADER_LOCKED = {bl}
AB_SLOTS = {ab_slots}
BOARD = {json.dumps(board)}
ABI = {json.dumps(abi)}

# Allow running directly or as part of the ForgeOS package tree.
# parents[3] resolves to the project root whether this file lives under
# devices/<session>/adapters/ or master/integrations/oem_adapters/.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.integrations import adb, fastboot  # noqa: E402


def probe(serial: str | None = None) -> dict[str, object]:
    """Check whether the device is visible over its expected transport."""
    if TRANSPORT in {{"usb-adb", "usb-recovery"}}:
        devices = adb.list_devices()
        for d in devices:
            if serial and d.get("serial") != serial:
                continue
            if (
                MODEL.upper() in d.get("model", "").upper()
                or CODENAME in d.get("device", "")
                or (serial and d.get("serial") == serial)
            ):
                return {{"visible": True, "transport": TRANSPORT, "serial": d["serial"]}}
        raw = adb.raw_devices()
        for d in raw:
            if d.get("status") == "unauthorized":
                return {{"visible": True, "transport": "usb-unauthorized", "serial": d.get("serial", "")}}
        return {{"visible": False, "transport": TRANSPORT, "reason": "no adb device found for this model"}}
    if TRANSPORT in {{"usb-fastboot", "usb-fastbootd"}}:
        devices = fastboot.list_devices()
        for d in devices:
            if serial and d.get("serial") != serial:
                continue
            return {{"visible": True, "transport": TRANSPORT, "serial": d["serial"]}}
        return {{"visible": False, "transport": TRANSPORT, "reason": "no fastboot device found"}}
    return {{"visible": False, "transport": TRANSPORT, "reason": "unknown transport"}}


def get_flash_commands(serial: str, artifact_path: str) -> list[dict[str, object]]:
    """Return ordered flash-command steps for this device and transport.

    All destructive steps carry requires_wipe_phrase=True so PolicyGuard can gate them.
    """
    steps: list[dict[str, object]] = []
    if TRANSPORT in {{"usb-adb", "usb-recovery"}}:
        steps.append({{
            "step": "reboot_to_recovery",
            "command": ["adb", "-s", serial, "reboot", "recovery"],
            "description": "Reboot device into recovery for sideload.",
            "safe": True,
            "requires_approval": False,
            "requires_wipe_phrase": False,
        }})
        steps.append({{
            "step": "sideload",
            "command": ["adb", "-s", serial, "sideload", artifact_path],
            "description": "ADB sideload the recovery-compatible package.",
            "safe": False,
            "requires_approval": True,
            "requires_wipe_phrase": True,
        }})
    elif TRANSPORT in {{"usb-fastboot"}}:
        slot = "_a" if AB_SLOTS else ""
        steps.append({{
            "step": "flash_system",
            "command": ["fastboot", "-s", serial, "flash", f"system{{slot}}", artifact_path],
            "description": f"Flash system image to partition system{{slot}}.",
            "safe": False,
            "requires_approval": True,
            "requires_wipe_phrase": True,
        }})
        if AB_SLOTS:
            steps.append({{
                "step": "set_active_slot",
                "command": ["fastboot", "-s", serial, "--set-active=a"],
                "description": "Set active boot slot to A after flash.",
                "safe": True,
                "requires_approval": False,
                "requires_wipe_phrase": False,
            }})
        steps.append({{
            "step": "reboot",
            "command": ["fastboot", "-s", serial, "reboot"],
            "description": "Reboot device after flash.",
            "safe": True,
            "requires_approval": False,
            "requires_wipe_phrase": False,
        }})
    return steps


def self_test() -> dict[str, object]:
    """Run probe and return a structured JSON result for promotion eligibility."""
    probe_result = probe()
    visible = bool(probe_result.get("visible"))
    status = "probe_pass" if visible else "probe_no_device"
    return {{
        "status": status,
        "adapter_key": ADAPTER_KEY,
        "manufacturer": MANUFACTURER,
        "model": MODEL,
        "codename": CODENAME,
        "transport": TRANSPORT,
        "bootloader_locked": BOOTLOADER_LOCKED,
        "ab_slots": AB_SLOTS,
        "board": BOARD,
        "abi": ABI,
        "probe": probe_result,
        "summary": (
            f"Adapter {{ADAPTER_KEY}} probe confirmed device visible over {{TRANSPORT}}."
            if visible
            else f"Adapter {{ADAPTER_KEY}}: device not connected at self-test time (adapter is still valid)."
        ),
    }}


if __name__ == "__main__":
    print(json.dumps(self_test()))
'''

    @staticmethod
    def _device_adapter_playbook(
        *,
        key: str,
        manufacturer: str,
        model: str,
        codename: str,
        transport: str,
    ) -> dict[str, Any]:
        source_hints = _source_hints_for(manufacturer, model, codename)
        states: dict[str, Any] = {
            "usb_only": {
                "title": f"Enable USB debugging on {manufacturer} {model}",
                "summary": (
                    f"ForgeOS can see the {manufacturer} {model} over USB but cannot yet manage it. "
                    "USB debugging must be enabled to continue."
                ),
                "steps": [
                    "Unlock the phone screen.",
                    "Open Settings and navigate to About phone (or About device).",
                    "Tap Build number 7 times to unlock Developer Options.",
                    "Return to Settings and open Developer Options.",
                    "Enable USB debugging.",
                    "Reconnect the USB cable if needed and select File transfer / MTP mode.",
                    "Approve the Allow USB debugging prompt when it appears on the phone.",
                ],
                "expected_next_state": "adb_unauthorized, then adb_connected after trust approval",
                "troubleshooting": [
                    "Use a data-capable USB cable, not a charge-only cable.",
                    f"{manufacturer} devices sometimes stay in MTP until the screen is unlocked during reconnect.",
                    "If the trust prompt never appears, toggle USB debugging off and back on.",
                ],
            },
            "adb_unauthorized": {
                "title": f"Approve USB debugging trust on {manufacturer} {model}",
                "summary": f"The {manufacturer} {model} is visible to adb but has not yet trusted this computer.",
                "steps": [
                    "Unlock the phone and watch for the Allow USB debugging dialog.",
                    "Tap Allow (or Always allow from this computer).",
                    "Keep the phone awake until ForgeOS shows adb connected.",
                ],
                "expected_next_state": "adb_connected",
                "troubleshooting": [
                    "If the prompt is missing, reconnect the cable while the phone is unlocked.",
                    "Revoke USB debugging authorizations in Developer Options and reconnect if stuck.",
                ],
            },
            "adb_connected": {
                "title": "adb transport ready",
                "summary": (
                    f"ForgeOS can now interrogate the {manufacturer} {model} non-destructively "
                    "and prepare backup and restore artifacts."
                ),
                "steps": [
                    "Keep the phone connected and unlocked.",
                    "Let ForgeOS capture backup metadata before any destructive action.",
                    "Review the flash plan and restore readiness before approving a wipe.",
                ],
                "expected_next_state": "assessment and backup capture",
                "troubleshooting": [],
            },
            "fastboot_connected": {
                "title": "fastboot transport ready",
                "summary": (
                    f"ForgeOS can perform low-level assessment and flash planning "
                    f"for the {manufacturer} {model} from fastboot."
                ),
                "steps": [
                    "Keep the device on the fastboot screen.",
                    "Wait for ForgeOS to capture low-level device facts.",
                    "Do not wipe or unlock anything until the restore path is reviewed.",
                ],
                "expected_next_state": "fastboot assessment",
                "troubleshooting": [],
            },
        }
        return {
            "playbook_id": key,
            "manufacturer": manufacturer,
            "model": model,
            "codename": codename,
            "transport": transport,
            "source_hints": source_hints,
            "states": states,
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
            task_id = "source-acquisition-and-staging"
            remediation_family = "source_acquisition_and_staging"
            objective = "Search known local firmware locations, learn from cached research, and stage compatible install artifacts into the active session."
        elif blocker_type == "subsystem_blocker":
            task_id = "followup-diagnostic"
            remediation_family = "followup_diagnostic"
            objective = "Generate a follow-up generic diagnostic after a previous remediation artifact failed to improve the session."
        return {
            "task_id": task_id,
            "blocker_type": blocker_type,
            "blocker_summary": blocker.get("summary", ""),
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
import re
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


def _copy_if_missing(source_path: Path, dest_path: Path) -> str:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not dest_path.exists():
        dest_path.write_bytes(source_path.read_bytes())
    return str(dest_path)


def _safe_read_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {{}}
    except Exception:
        return {{}}


def _source_search_roots() -> list[Path]:
    roots = [
        ROOT / "downloads",
        ROOT / "artifacts",
        ROOT / "output",
        Path.home() / "Downloads",
    ]
    devices_root = ROOT / "devices"
    if devices_root.exists():
        roots.extend(
            path / "artifacts" / "os-source"
            for path in devices_root.iterdir()
            if path.is_dir() and path != SESSION_DIR
        )
    seen: set[str] = set()
    unique_roots: list[Path] = []
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)
        unique_roots.append(root)
    return unique_roots


def _candidate_keywords() -> list[str]:
    backup = _safe_read_json(SESSION_DIR / "backup" / "device-metadata-backup.json")
    metadata = backup.get("captures", {{}}) if isinstance(backup.get("captures"), dict) else {{}}
    getprop_stdout = ""
    if isinstance(metadata.get("getprop"), dict):
        getprop_stdout = str(metadata["getprop"].get("stdout", ""))
    props = {{}}
    for line in getprop_stdout.splitlines():
        match = re.match(r"\\[(.+?)\\]:\\s*\\[(.*)?\\]", line)
        if match:
            props[match.group(1)] = match.group(2)
    parts = [
        props.get("ro.product.manufacturer", ""),
        props.get("ro.product.brand", ""),
        props.get("ro.product.model", ""),
        props.get("ro.product.device", ""),
        props.get("ro.product.name", ""),
        props.get("ro.build.product", ""),
    ]
    task_path = SESSION_DIR / "codegen" / "remediation-task.json"
    task_data = _safe_read_json(task_path)
    summary = str(task_data.get("blocker_summary", ""))
    parts.extend(re.findall(r"[A-Za-z0-9_-]{{4,}}", summary))
    keywords = []
    seen = set()
    for part in parts:
        cleaned = re.sub(r"[^a-z0-9]+", "", str(part).lower())
        if len(cleaned) < 4 or cleaned in seen:
            continue
        seen.add(cleaned)
        keywords.append(cleaned)
    return keywords


def _candidate_score(path: Path, keywords: list[str]) -> int:
    name = path.name.lower()
    normalized_name = re.sub(r"[^a-z0-9]+", "", name)
    score = 0
    if name in {"update.zip", "ota.zip", "payload.zip"}:
        score += 10
    if path.suffix == ".img":
        score += 6
    for keyword in keywords:
        if keyword and (keyword in name or keyword in normalized_name):
            score += 3
    return score


def _find_local_source_candidates(keywords: list[str]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for root in _source_search_roots():
        if not root.exists():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_file():
                continue
            if entry.name == "README.md" or entry.suffix.lower() not in {".zip", ".img", ".gz", ".tar", ".bin"}:
                continue
            score = _candidate_score(entry, keywords)
            if score <= 0:
                continue
            candidates.append({{
                "path": str(entry),
                "name": entry.name,
                "score": score,
                "root": str(root),
            }})
    candidates.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
    return candidates


def _stage_source_candidates() -> dict[str, object]:
    source_dir = SESSION_DIR / "artifacts" / "os-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    keywords = _candidate_keywords()
    research_path = SESSION_DIR / "research" / "firmware_sources.json"
    research = _safe_read_json(research_path) if research_path.exists() else {{}}
    candidates = _find_local_source_candidates(keywords)
    staged: list[str] = []

    sideload_names = {"update.zip", "ota.zip", "payload.zip"}
    staged_zip = False
    for candidate in candidates:
        candidate_path = Path(str(candidate["path"]))
        if candidate_path.name in sideload_names or (
            candidate_path.suffix.lower() == ".zip" and not staged_zip
        ):
            staged.append(_copy_if_missing(candidate_path, source_dir / candidate_path.name))
            staged_zip = True
            break

    fastboot_names = {{
        "boot.img",
        "init_boot.img",
        "vendor_boot.img",
        "dtbo.img",
        "vbmeta.img",
        "vbmeta_system.img",
        "recovery.img",
        "system.img",
        "vendor.img",
        "product.img",
        "super.img",
    }}
    selected_fastboot = [c for c in candidates if str(c["name"]) in fastboot_names]
    if selected_fastboot:
        for candidate in selected_fastboot:
            candidate_path = Path(str(candidate["path"]))
            staged.append(_copy_if_missing(candidate_path, source_dir / candidate_path.name))

    acquisition_plan = {{
        "generated_at": {json.dumps(utc_now())},
        "source_dir": str(source_dir),
        "keywords": keywords,
        "candidate_count": len(candidates),
        "local_candidates": candidates[:12],
        "staged_files": staged,
        "research_summary": {{
            "firmware_sources": research.get("firmware_sources", []),
            "community_notes": research.get("community_notes", ""),
            "flash_procedure_hints": research.get("flash_procedure_hints", []),
            "unlock_procedure": research.get("unlock_procedure", ""),
        }},
    }}
    plan_path = SESSION_DIR / "plans" / "source-acquisition-plan.json"
    _write_json(plan_path, acquisition_plan)
    return {{
        "plan_path": str(plan_path),
        "source_dir": str(source_dir),
        "local_candidates": candidates[:12],
        "staged_files": staged,
        "research_available": research_path.exists(),
    }}


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

    if REMEDIATION_FAMILY == "source_acquisition_and_staging":
        acquisition = _stage_source_candidates()
        result = {{
            "status": "solved",
            "summary": (
                "ForgeOS searched local firmware sources and staged any compatible artifacts it could find."
                if acquisition.get("staged_files")
                else "ForgeOS searched local firmware sources, refreshed its acquisition plan, and is ready for another source classification pass."
            ),
            "evidence": {{
                **evidence,
                "diagnostics_path": diagnostics_path,
                "partition_probe_path": partition_probe_path,
                "build_candidates_path": build_candidates_path,
                "source_acquisition": acquisition,
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

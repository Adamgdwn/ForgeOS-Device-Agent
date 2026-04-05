from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from app.core.host_capabilities import discover_host_capabilities
from app.core.models import PreviewExecution, VerificationExecution, to_dict
from app.integrations import adb, fastboot


def _safe_run(command: list[str], cwd: Path | None = None, timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


class PreviewPipeline:
    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self,
        session_dir: Path,
        build_plan: dict[str, Any],
        recommendation: dict[str, Any],
        assessment: dict[str, Any],
        connection_plan: dict[str, Any],
    ) -> PreviewExecution:
        preview_dir = session_dir / "runtime" / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        host = discover_host_capabilities(self.root)

        capability_matrix = {
            "resolved_path": build_plan.get("os_path", "unknown"),
            "recommended_use_case": recommendation.get("recommended_use_case", "unknown"),
            "support_status": assessment.get("support_status", "unknown"),
            "transport_readiness": connection_plan.get("recommended_adapter", {}).get("adapter_id", "unknown"),
            "host_emulator_available": host.get("emulator_available", False),
            "available_avds": host.get("available_avds", []),
        }
        matrix_path = preview_dir / "capability-matrix.json"
        matrix_path.write_text(json.dumps(capability_matrix, indent=2))

        steps: list[dict[str, Any]] = []
        generated_files = [str(matrix_path)]
        mode = "simulated"
        summary = "ForgeOS executed a simulated preview pipeline and generated a reviewable preview bundle."

        if host.get("emulator_available") and host.get("available_avds"):
            avd = host["available_avds"][0]
            emulator_exec = shutil.which("emulator")
            launch_probe = _safe_run([emulator_exec, "-list-avds"]) if emulator_exec else {"ok": False, "stderr": "emulator unavailable"}
            steps.append(
                {
                    "name": "emulator_probe",
                    "status": "completed" if launch_probe.get("ok") else "failed",
                    "detail": launch_probe.get("stdout") or launch_probe.get("stderr", ""),
                    "avd": avd,
                }
            )
            if launch_probe.get("ok"):
                mode = "emulator_probe"
                summary = "ForgeOS executed an emulator-backed preview probe and generated companion preview artifacts."
        else:
            steps.append(
                {
                    "name": "emulator_probe",
                    "status": "skipped",
                    "detail": host.get("reasons", {}).get("emulator", "Emulator unavailable."),
                }
            )

        walkthrough_lines = [
            "# ForgeOS Preview",
            "",
            f"Recommended use case: {recommendation.get('recommended_use_case', 'unknown')}",
            f"Resolved path: {build_plan.get('os_path', 'unknown')}",
            f"Support status: {assessment.get('support_status', 'unknown')}",
            f"Preview mode: {mode}",
            "",
            "## Operator-facing simulation",
            "",
            "1. Device boots into a simplified, task-oriented experience.",
            "2. Recovery and restore notes remain visible to the operator.",
            "3. Limitations discovered during assessment remain explicitly listed before install.",
        ]
        walkthrough_path = preview_dir / "simulated-walkthrough.md"
        walkthrough_path.write_text("\n".join(walkthrough_lines))
        generated_files.append(str(walkthrough_path))
        steps.append({"name": "simulated_walkthrough", "status": "completed"})

        feature_lines = "\n".join(
            f"- {label}"
            for label in build_plan.get("included_feature_labels", [])[:8]
        ) or "- Default profile features are still being used."
        held_back_lines = "\n".join(
            f"- {label}"
            for label in build_plan.get("rejected_feature_labels", [])[:6]
        ) or "- No explicit feature exclusions recorded yet."
        experience_preview_path = preview_dir / "experience-preview.md"
        experience_preview_path.write_text(
            "\n".join(
                [
                    "# Experience Preview",
                    "",
                    f"Proposed OS profile: {build_plan.get('proposed_os_name', 'Unknown build profile')}",
                    f"Resolved build path: {build_plan.get('os_path', 'unknown')}",
                    "",
                    "## What the device should feel like",
                    "",
                    "- Boot into a simplified, operator-reviewed experience.",
                    "- Keep restore and rollback guidance visible before any destructive action.",
                    "- Preserve the chosen safety and usability features from the review panel.",
                    "",
                    "## Included features",
                    "",
                    feature_lines,
                    "",
                    "## Held back or default-off items",
                    "",
                    held_back_lines,
                    "",
                    "## Home-screen sketch",
                    "",
                    "```text",
                    "+--------------------------------------+",
                    "| ForgeOS Home                         |",
                    "|--------------------------------------|",
                    "| Phone  Messages  Camera  Help        |",
                    "|                                      |",
                    "| Accessibility  Battery  Restore      |",
                    "|                                      |",
                    "| Trusted Contacts  Notes  Updates     |",
                    "+--------------------------------------+",
                    "```",
                ]
            )
        )
        generated_files.append(str(experience_preview_path))
        steps.append({"name": "experience_preview", "status": "completed"})

        next_steps_path = preview_dir / "next-steps.md"
        next_steps_path.write_text(
            "\n".join(
                [
                    "# Next Steps",
                    "",
                    "1. Review the proposed OS profile and feature selections in the GUI.",
                    "2. Open the preview bundle and confirm the experience preview matches the intended user.",
                    "3. Confirm backup and restore readiness before any install approval is recorded.",
                    "4. Save the Verification Review decisions so ForgeOS can carry them into install planning.",
                    "5. Use the dry run before any live destructive execution.",
                ]
            )
        )
        generated_files.append(str(next_steps_path))
        steps.append({"name": "next_steps", "status": "completed"})

        preview_bundle_path = preview_dir / "proposed-os-preview.tar.gz"
        with tarfile.open(preview_bundle_path, "w:gz") as tar:
            for path in [matrix_path, walkthrough_path, experience_preview_path, next_steps_path]:
                tar.add(path, arcname=path.name)
        generated_files.append(str(preview_bundle_path))
        steps.append(
            {
                "name": "preview_bundle",
                "status": "completed",
                "detail": str(preview_bundle_path),
            }
        )

        execution = PreviewExecution(
            status="executed",
            summary=summary,
            mode=mode,
            generated_files=generated_files,
            steps=steps,
            capability_matrix=capability_matrix,
        )
        execution_path = preview_dir / "preview-execution.json"
        execution_path.write_text(json.dumps(to_dict(execution), indent=2))
        execution.generated_files.append(str(execution_path))
        return execution

    def defer(
        self,
        session_dir: Path,
        *,
        reason: str,
        build_plan: dict[str, Any],
        recommendation: dict[str, Any],
        assessment: dict[str, Any],
        connection_plan: dict[str, Any],
    ) -> PreviewExecution:
        preview_dir = session_dir / "runtime" / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        capability_matrix = {
            "resolved_path": build_plan.get("os_path", "unknown"),
            "recommended_use_case": recommendation.get("recommended_use_case", "unknown"),
            "support_status": assessment.get("support_status", "unknown"),
            "transport_readiness": connection_plan.get("recommended_adapter", {}).get("adapter_id", "unknown"),
            "deferred_reason": reason,
        }
        execution = PreviewExecution(
            status="deferred",
            summary=reason,
            mode="deferred",
            generated_files=[],
            steps=[{"name": "preview_gate", "status": "deferred", "detail": reason}],
            capability_matrix=capability_matrix,
        )
        execution_path = preview_dir / "preview-execution.json"
        execution_path.write_text(json.dumps(to_dict(execution), indent=2))
        execution.generated_files.append(str(execution_path))
        return execution


class VerificationPipeline:
    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self,
        session_dir: Path,
        assessment: dict[str, Any],
        backup_plan: dict[str, Any],
        restore_plan: dict[str, Any],
        flash_plan: dict[str, Any],
    ) -> VerificationExecution:
        verification_dir = session_dir / "runtime" / "verification"
        verification_dir.mkdir(parents=True, exist_ok=True)

        host = discover_host_capabilities(self.root)
        checkpoints: list[dict[str, Any]] = []
        interactive_checks: list[dict[str, Any]] = []

        checkpoints.append(
            {
                "name": "support_status",
                "status": "passed" if assessment.get("support_status") != "blocked" else "warning",
                "detail": assessment.get("summary", "No assessment summary available."),
            }
        )
        checkpoints.append(
            {
                "name": "host_adb",
                "status": "passed" if host.get("adb_available") else "warning",
                "detail": "adb is available." if host.get("adb_available") else "adb is unavailable on this host.",
            }
        )
        checkpoints.append(
            {
                "name": "host_fastboot",
                "status": "passed" if host.get("fastboot_available") else "warning",
                "detail": "fastboot is available." if host.get("fastboot_available") else "fastboot is unavailable on this host.",
            }
        )
        checkpoints.append(
            {
                "name": "backup_bundle",
                "status": "passed" if backup_plan.get("backup_bundle_path") else "warning",
                "detail": "Pre-wipe backup bundle captured." if backup_plan.get("backup_bundle_path") else "Backup bundle is missing.",
            }
        )
        checkpoints.append(
            {
                "name": "restore_readiness",
                "status": "passed" if (restore_plan.get("restore_plan_path") or restore_plan.get("details")) else "warning",
                "detail": "Restore plan is recorded." if (restore_plan.get("restore_plan_path") or restore_plan.get("details")) else "Restore plan is missing.",
            }
        )
        checkpoints.append(
            {
                "name": "flash_path",
                "status": "passed" if flash_plan.get("build_path") else "pending",
                "detail": "Flash path is recorded." if flash_plan.get("build_path") else "Flash path is not ready yet.",
            }
        )

        adb_devices = adb.list_devices()
        raw_adb = adb.raw_devices()
        fastboot_devices = fastboot.list_devices()
        checkpoints.append(
            {
                "name": "adb_transport",
                "status": "passed" if adb_devices else ("warning" if raw_adb else "pending"),
                "detail": f"adb device count: {len(adb_devices)}; raw entries: {len(raw_adb)}",
            }
        )
        checkpoints.append(
            {
                "name": "fastboot_transport",
                "status": "passed" if fastboot_devices else "pending",
                "detail": f"fastboot device count: {len(fastboot_devices)}",
            }
        )

        if adb_devices:
            serial = adb_devices[0]["serial"]
            getprop = adb.shell(serial, ["getprop", "ro.build.fingerprint"])
            battery = adb.shell(serial, ["dumpsys", "battery"])
            checkpoints.append(
                {
                    "name": "adb_getprop_probe",
                    "status": "passed" if getprop.get("ok") else "warning",
                    "detail": getprop.get("stdout", "")[:240] or getprop.get("stderr", ""),
                }
            )
            checkpoints.append(
                {
                    "name": "adb_battery_probe",
                    "status": "passed" if battery.get("ok") else "warning",
                    "detail": battery.get("stdout", "")[:240] or battery.get("stderr", ""),
                }
            )

        interactive_checks.extend(
            [
                {
                    "prompt": "Confirm the recommended use case still matches the intended user.",
                    "status": "pending_operator_review",
                },
                {
                    "prompt": "Confirm restore notes are understandable before install.",
                    "status": "pending_operator_review",
                },
                {
                    "prompt": "Review known limitations before destructive actions.",
                    "status": "pending_operator_review",
                },
            ]
        )

        execution = VerificationExecution(
            status="executed",
            summary="ForgeOS executed host-side and transport-aware verification checks and recorded operator review items.",
            checkpoints=checkpoints,
            interactive_checks=interactive_checks,
            generated_files=[],
        )
        execution_path = verification_dir / "verification-execution.json"
        execution_path.write_text(json.dumps(to_dict(execution), indent=2))
        execution.generated_files.append(str(execution_path))
        return execution

    def defer(
        self,
        session_dir: Path,
        *,
        reason: str,
    ) -> VerificationExecution:
        verification_dir = session_dir / "runtime" / "verification"
        verification_dir.mkdir(parents=True, exist_ok=True)
        execution = VerificationExecution(
            status="deferred",
            summary=reason,
            checkpoints=[
                {
                    "name": "verification_gate",
                    "status": "deferred",
                    "detail": reason,
                }
            ],
            interactive_checks=[],
            generated_files=[],
        )
        execution_path = verification_dir / "verification-execution.json"
        execution_path.write_text(json.dumps(to_dict(execution), indent=2))
        execution.generated_files.append(str(execution_path))
        return execution

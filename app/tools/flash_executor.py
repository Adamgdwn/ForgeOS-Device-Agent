from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import DestructiveApproval, FlashPlan, PolicyModel, Transport
from app.tools.base import BaseTool


class FlashExecutorTool(BaseTool):
    name = "flash_executor"
    input_schema = {
        "flash_plan": "object",
        "approval": "object",
        "policy": "object",
        "device": "object",
        "session_dir": "string",
    }
    output_schema = {"status": "string", "summary": "string", "details": "object"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def build_plan(
        self,
        session_id: str,
        device: dict[str, Any],
        assessment: dict[str, Any],
        build_plan: dict[str, Any],
        backup_plan: dict[str, Any],
        policy: PolicyModel,
        live_mode: bool = False,
    ) -> FlashPlan:
        support_status = assessment.get("support_status", "research_only")
        restore_path_available = support_status == "actionable"
        transport = device.get("transport", Transport.UNKNOWN.value)
        install_deferred = support_status != "actionable" or build_plan.get("os_path") == "research_only_path"
        selected_option_label = build_plan.get("selected_option_label", "the proposed device profile")
        included_feature_labels = list(build_plan.get("included_feature_labels", []))
        rejected_feature_labels = list(build_plan.get("rejected_feature_labels", []))
        steps = [
            {
                "name": "preflight_checks",
                "kind": "verification",
                "destructive": False,
                "description": "Confirm transport, power stability, and host tooling readiness.",
            },
            {
                "name": "verify_backup_bundle",
                "kind": "safety",
                "destructive": False,
                "description": (
                    f"Confirm the pre-wipe backup bundle exists at {backup_plan.get('backup_bundle_path', 'unknown')}."
                ),
            },
            {
                "name": "restore_checkpoint",
                "kind": "safety",
                "destructive": False,
                "description": "Record restore and rollback metadata before touching partitions.",
            },
            {
                "name": "wipe_userdata",
                "kind": "wipe",
                "destructive": True,
                "description": "Wipe user data and prepare a clean installation target.",
            },
            {
                "name": "flash_images",
                "kind": "flash",
                "destructive": True,
                "description": f"Flash the selected image set for `{selected_option_label}` on the resolved OS path.",
            },
            {
                "name": "boot_validation",
                "kind": "validation",
                "destructive": False,
                "description": "Boot the device and verify initial connectivity and integrity.",
            },
        ]
        if live_mode and not policy.allow_live_destructive_actions:
            live_mode = False
        return FlashPlan(
            session_id=session_id,
            build_path=build_plan.get("os_path", "unknown"),
            dry_run=not live_mode,
            requires_unlock=transport in {Transport.USB_FASTBOOT.value, Transport.USB_FASTBOOTD.value},
            requires_wipe=True,
            restore_path_available=restore_path_available,
            transport=transport,
            step_count=len(steps),
            steps=steps,
            artifact_hints=build_plan.get("artifact_requirements", []),
            status="deferred" if install_deferred else "planned",
            summary=(
                "Install planning is deferred while ForgeOS continues research, recommendation, preview, and verification."
                if install_deferred
                else (
                    "Prepared a conservative flash plan with preflight, backup verification, restore checkpoint, wipe, flash, and validation phases "
                    f"for {selected_option_label}. Included features: {', '.join(included_feature_labels[:4]) or 'default profile features'}. "
                    f"Held back: {', '.join(rejected_feature_labels[:3]) or 'no explicit feature rejections recorded yet'}."
                )
            ),
        )

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        session_dir = Path(str(payload["session_dir"]))
        flash_plan = FlashPlan(**dict(payload["flash_plan"])) if isinstance(payload["flash_plan"], dict) else payload["flash_plan"]
        approval = (
            DestructiveApproval(**dict(payload["approval"]))
            if isinstance(payload["approval"], dict)
            else payload["approval"]
        )
        policy = PolicyModel(**dict(payload["policy"])) if isinstance(payload["policy"], dict) else payload["policy"]
        dry_run = bool(payload.get("dry_run", True))

        transcript_path = session_dir / "execution" / "flash-transcript.json"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)

        if not approval.approved:
            result = {
                "status": "awaiting_approval",
                "summary": "Destructive execution is blocked until the operator grants explicit wipe approval.",
                "details": {
                    "dry_run": True,
                    "can_execute": False,
                    "reason": "approval_missing",
                    "transcript_path": str(transcript_path),
                },
            }
            transcript_path.write_text(json.dumps(result, indent=2))
            return result

        if policy.require_explicit_wipe_phrase and approval.confirmation_phrase.strip() != "WIPE_AND_REBUILD":
            result = {
                "status": "approval_invalid",
                "summary": "The destructive approval record is present, but the confirmation phrase is missing or incorrect.",
                "details": {
                    "dry_run": True,
                    "can_execute": False,
                    "reason": "invalid_confirmation_phrase",
                    "transcript_path": str(transcript_path),
                },
            }
            transcript_path.write_text(json.dumps(result, indent=2))
            return result

        if policy.require_restore_path and not (flash_plan.restore_path_available and approval.restore_path_confirmed):
            result = {
                "status": "blocked_no_restore_path",
                "summary": "Live destructive execution is blocked because a restore path is not yet confirmed.",
                "details": {
                    "dry_run": True,
                    "can_execute": False,
                    "reason": "restore_path_not_confirmed",
                    "transcript_path": str(transcript_path),
                },
            }
            transcript_path.write_text(json.dumps(result, indent=2))
            return result

        effective_dry_run = dry_run or flash_plan.dry_run or not policy.allow_live_destructive_actions
        executed_steps = []
        for index, step in enumerate(flash_plan.steps, start=1):
            executed_steps.append(
                {
                    "step_number": index,
                    "name": step.get("name", f"step_{index}"),
                    "kind": step.get("kind", "unknown"),
                    "destructive": step.get("destructive", False),
                    "mode": "dry_run" if effective_dry_run else "live_stub",
                    "status": "planned" if effective_dry_run else "queued_for_adapter_execution",
                    "description": step.get("description", ""),
                }
            )

        status = "dry_run_complete" if effective_dry_run else "live_execution_queued"
        summary = (
            "Dry run completed. ForgeOS recorded the approved wipe-and-rebuild sequence without touching the device."
            if effective_dry_run
            else "Live execution has been approved and queued. Device-specific adapter execution is the next step."
        )
        result = {
            "status": status,
            "summary": summary,
            "details": {
                "dry_run": effective_dry_run,
                "can_execute": True,
                "restore_path_available": flash_plan.restore_path_available,
                "approved_scope": approval.approval_scope,
                "build_path": flash_plan.build_path,
                "transport": flash_plan.transport,
                "transcript_path": str(transcript_path),
                "steps": executed_steps,
            },
        }
        transcript_path.write_text(json.dumps(result, indent=2))
        return result

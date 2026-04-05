from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import PreviewExecution, VerificationExecution, to_dict


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

        capability_matrix = {
            "resolved_path": build_plan.get("os_path", "unknown"),
            "recommended_use_case": recommendation.get("recommended_use_case", "unknown"),
            "support_status": assessment.get("support_status", "unknown"),
            "transport_readiness": connection_plan.get("recommended_adapter", {}).get("adapter_id", "unknown"),
            "preview_type": "simulated",
        }
        matrix_path = preview_dir / "capability-matrix.json"
        matrix_path.write_text(json.dumps(capability_matrix, indent=2))

        walkthrough_lines = [
            "# ForgeOS Preview",
            "",
            f"Recommended use case: {recommendation.get('recommended_use_case', 'unknown')}",
            f"Resolved path: {build_plan.get('os_path', 'unknown')}",
            f"Support status: {assessment.get('support_status', 'unknown')}",
            "",
            "## Simulated UX",
            "",
            "1. Device boots into a simplified, task-oriented experience.",
            "2. Recovery and restore notes remain visible to the operator.",
            "3. Limitations discovered during assessment remain explicitly listed before install.",
        ]
        walkthrough_path = preview_dir / "simulated-walkthrough.md"
        walkthrough_path.write_text("\n".join(walkthrough_lines))

        execution = PreviewExecution(
            status="executed",
            summary="ForgeOS executed the first preview pipeline and generated a simulated walkthrough plus capability matrix.",
            mode="simulated",
            generated_files=[str(matrix_path), str(walkthrough_path)],
            steps=[
                {"name": "capability_matrix", "status": "completed"},
                {"name": "simulated_walkthrough", "status": "completed"},
            ],
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

        backup_bundle = bool(backup_plan.get("backup_bundle_path"))
        restore_ready = bool(restore_plan.get("restore_plan_path") or restore_plan.get("details"))
        flash_ready = bool(flash_plan.get("build_path"))

        checkpoints = [
            {
                "name": "support_status",
                "status": "passed" if assessment.get("support_status") != "blocked" else "warning",
                "detail": assessment.get("summary", "No assessment summary available."),
            },
            {
                "name": "backup_bundle",
                "status": "passed" if backup_bundle else "warning",
                "detail": "Pre-wipe backup bundle captured." if backup_bundle else "Backup bundle is missing.",
            },
            {
                "name": "restore_readiness",
                "status": "passed" if restore_ready else "warning",
                "detail": "Restore plan is recorded." if restore_ready else "Restore plan is missing.",
            },
            {
                "name": "flash_path",
                "status": "passed" if flash_ready else "pending",
                "detail": "Flash path is recorded." if flash_ready else "Flash path is not ready yet.",
            },
        ]
        interactive_checks = [
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

        execution = VerificationExecution(
            status="executed",
            summary="ForgeOS executed the first verification pipeline and recorded deterministic pre-install checks plus operator review items.",
            checkpoints=checkpoints,
            interactive_checks=interactive_checks,
            generated_files=[],
        )
        execution_path = verification_dir / "verification-execution.json"
        execution_path.write_text(json.dumps(to_dict(execution), indent=2))
        execution.generated_files.append(str(execution_path))
        return execution

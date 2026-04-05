from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import BlockerType, DeviceProfile, SessionState, utc_now


class BlockerEngine:
    def __init__(self, root: Path) -> None:
        self.root = root

    def classify(
        self,
        profile: DeviceProfile,
        session_state: SessionState,
        assessment: dict[str, Any],
        engagement: dict[str, Any],
        connection_plan: dict[str, Any],
    ) -> dict[str, Any]:
        transport = profile.transport.value
        engagement_status = engagement.get("engagement_status", "unknown")
        next_steps = engagement.get("next_steps") or []
        machine_solvable = True
        blocker_type = BlockerType.NONE
        summary = "No immediate blocker classified."
        escalation_condition = "None"

        if transport == "usb-mtp" or engagement_status == "usb_only_detected":
            blocker_type = BlockerType.TRANSPORT
            machine_solvable = False
            summary = (
                "The phone is visible by USB but does not yet expose a manageable transport like adb, fastboot, or recovery."
            )
            escalation_condition = "Wait for user-side device action or alternate OEM transport."
        elif engagement_status == "awaiting_user_approval":
            blocker_type = BlockerType.TRUST
            machine_solvable = False
            summary = "The phone is visible to adb but still requires on-device trust approval."
            escalation_condition = "Wait for user to approve USB debugging prompt."
        elif assessment.get("support_status") == "blocked":
            blocker_type = BlockerType.POLICY
            machine_solvable = False
            summary = assessment.get("summary", "A hard support blocker was identified.")
            escalation_condition = "Do not proceed without new evidence or a safer alternative path."
        elif connection_plan.get("requires_codex_generation"):
            blocker_type = BlockerType.SOURCE
            machine_solvable = True
            summary = "Connection/build path requires generated session-specific code or configuration."
            escalation_condition = "Escalate only if generated artifacts fail to improve the path."

        recommended_adapter = connection_plan.get("recommended_adapter") or {}
        return {
            "generated_at": utc_now(),
            "blocker_type": blocker_type.value,
            "confidence": 0.85 if blocker_type != BlockerType.NONE else 0.35,
            "machine_solvable": machine_solvable,
            "summary": summary,
            "required_artifacts": [
                "device-profile.json",
                "session-state.json",
                "reports/assessment.json",
                "reports/engagement.json",
                "plans/connection-plan.json",
            ],
            "planned_next_action": recommended_adapter.get("adapter_id", "observe"),
            "retry_budget": 2 if machine_solvable else 0,
            "escalation_condition": escalation_condition,
            "user_steps": next_steps,
        }

    def write(self, session_dir: Path, payload: dict[str, Any]) -> Path:
        path = session_dir / "reports" / "blocker.json"
        path.write_text(json.dumps(payload, indent=2))
        return path

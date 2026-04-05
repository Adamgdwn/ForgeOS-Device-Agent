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
        remediation_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        transport = profile.transport.value
        engagement_status = engagement.get("engagement_status", "unknown")
        next_steps = engagement.get("next_steps") or []
        remediation_result = remediation_result or {}
        remediation_status = remediation_result.get("status", "")
        machine_solvable = True
        blocker_type = BlockerType.NONE
        summary = "No immediate blocker classified."
        escalation_condition = "None"
        retry_budget = 1
        planned_next_action = (connection_plan.get("recommended_adapter") or {}).get("adapter_id", "observe")

        if remediation_status == "solved":
            blocker_type = BlockerType.NONE
            machine_solvable = False
            summary = "The most recent remediation artifact improved the session enough to continue the main plan."
            escalation_condition = "None"
            retry_budget = 0
            planned_next_action = "continue_main_plan"
        elif transport == "usb-mtp" or engagement_status == "usb_only_detected":
            blocker_type = BlockerType.TRANSPORT
            machine_solvable = True
            summary = (
                "The phone is visible by USB but does not yet expose a fully managed transport. ForgeOS should generate generic host-side triage and transport diagnostics before pausing."
            )
            escalation_condition = "Pause only if generated transport triage still shows that the phone needs a physical on-device action."
            retry_budget = 2
            planned_next_action = "generate_host_transport_triage"
        elif engagement_status == "awaiting_user_approval":
            blocker_type = BlockerType.TRUST
            machine_solvable = False
            summary = "The phone is visible to adb but still requires on-device trust approval."
            escalation_condition = "Wait for user to approve USB debugging prompt."
            retry_budget = 0
            planned_next_action = "ask_for_usb_debugging_trust"
        elif assessment.get("support_status") == "blocked":
            blocker_type = BlockerType.POLICY
            machine_solvable = False
            summary = assessment.get("summary", "A hard support blocker was identified.")
            escalation_condition = "Do not proceed without new evidence or a safer alternative path."
            retry_budget = 0
            planned_next_action = "halt_with_evidence"
        elif connection_plan.get("requires_codex_generation"):
            blocker_type = BlockerType.SOURCE
            machine_solvable = True
            summary = "Connection/build path requires generated session-specific code or configuration."
            escalation_condition = "Escalate only if generated artifacts fail to improve the path."
            retry_budget = 2
            planned_next_action = "generate_generic_adapter_scaffold"
        elif remediation_status == "needs_user_action":
            blocker_type = BlockerType.PHYSICAL
            machine_solvable = False
            summary = remediation_result.get("summary", "The latest remediation artifact concluded that a physical device action is required.")
            escalation_condition = "Ask one minimal operational question and preserve the current rollback posture."
            retry_budget = 0
            planned_next_action = "question_gate"
        elif remediation_status == "artifact_failed":
            blocker_type = BlockerType.SUBSYSTEM
            machine_solvable = session_state.remediation_iteration < 2
            summary = remediation_result.get("summary", "The remediation artifact failed and needs another generated attempt or review.")
            escalation_condition = "Stop autonomous retries if repeated generated artifacts fail without improving evidence."
            retry_budget = max(0, 2 - session_state.remediation_iteration)
            planned_next_action = "generate_followup_diagnostic"

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
            "planned_next_action": planned_next_action,
            "retry_budget": retry_budget if machine_solvable else 0,
            "escalation_condition": escalation_condition,
            "user_steps": next_steps,
            "remediation_status": remediation_status or "not_started",
        }

    def write(self, session_dir: Path, payload: dict[str, Any]) -> Path:
        path = session_dir / "reports" / "blocker.json"
        path.write_text(json.dumps(payload, indent=2))
        return path

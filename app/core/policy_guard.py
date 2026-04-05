from __future__ import annotations

from pathlib import Path

from app.core.models import ApprovalGate, AuditEntry, DestructiveApproval, FlashPlan, PolicyModel


class PolicyGuard:
    def __init__(self, root: Path) -> None:
        self.root = root

    def evaluate_install_gate(
        self,
        policy: PolicyModel,
        flash_plan: FlashPlan,
        approval: DestructiveApproval,
        backup_plan: dict[str, object],
    ) -> ApprovalGate:
        missing: list[str] = []
        consequences = [
            "User data may be wiped.",
            "An interrupted install may require manual recovery tooling.",
            "Restore depends on the recorded backup bundle and available vendor images.",
        ]

        if not backup_plan:
            missing.append("Pre-wipe backup bundle has not been captured.")
        if policy.require_restore_path and not flash_plan.restore_path_available:
            missing.append("A restore path is not yet feasible for this device path.")
        if policy.require_restore_path and not approval.restore_path_confirmed:
            missing.append("Operator has not confirmed the restore path.")
        if not approval.approved:
            missing.append("Explicit destructive approval has not been granted.")
        if policy.require_explicit_wipe_phrase and approval.confirmation_phrase.strip() != "WIPE_AND_REBUILD":
            missing.append("The wipe confirmation phrase is missing or incorrect.")

        return ApprovalGate(
            action="wipe_and_install",
            allowed=not missing,
            requires_explicit_approval=True,
            reason=(
                "Install can proceed."
                if not missing
                else "Install remains blocked until deterministic safety requirements are satisfied."
            ),
            missing_requirements=missing,
            consequences=consequences,
        )

    def evaluate_research_gate(self, blocker: dict[str, object]) -> ApprovalGate:
        machine_solvable = bool(blocker.get("machine_solvable"))
        reason = (
            "ForgeOS should continue autonomous remediation."
            if machine_solvable
            else "ForgeOS must pause for a physical action, missing artifact, or approval boundary."
        )
        return ApprovalGate(
            action="autonomous_runtime_progress",
            allowed=machine_solvable,
            requires_explicit_approval=False,
            reason=reason,
            missing_requirements=[] if machine_solvable else list(blocker.get("user_steps", [])),
            consequences=[],
        )

    def build_audit_entry(
        self,
        category: str,
        message: str,
        evidence: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditEntry:
        return AuditEntry(
            category=category,
            message=message,
            evidence=evidence or [],
            metadata=metadata or {},
        )

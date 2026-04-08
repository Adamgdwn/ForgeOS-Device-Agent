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
        if not flash_plan.artifacts_ready:
            missing.append("A flashable artifact bundle has not been staged for this session.")
        if policy.require_restore_path and not flash_plan.restore_path_available:
            missing.append("A restore path is not yet feasible for this device path.")
        if policy.require_restore_path and not approval.restore_path_confirmed:
            missing.append("Operator has not confirmed the restore path.")
        if policy.destructive_ops_require_approval and not approval.approved:
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

    def evaluate_self_improvement_gate(
        self,
        *,
        policy: PolicyModel,
        session_dir: Path,
        estimated_tokens_used: int,
        iteration_count: int,
        proposed_paths: list[Path],
    ) -> ApprovalGate:
        missing: list[str] = []
        allowed_scopes = list(policy.self_modification_scope or [])
        for path in proposed_paths:
            if not self._path_allowed(session_dir, path, allowed_scopes):
                missing.append(f"Self-modification path is outside policy scope: {path}")
        if estimated_tokens_used >= policy.max_api_tokens_per_session:
            missing.append("Session token budget for autonomous experiments has been exhausted.")
        if iteration_count >= policy.max_experiment_loop_iterations:
            missing.append("Autonomous experiment loop iteration budget has been exhausted.")
        return ApprovalGate(
            action="self_improvement_loop",
            allowed=not missing,
            requires_explicit_approval=False,
            reason=(
                "Self-improvement loop may continue within policy limits."
                if not missing
                else "Self-improvement loop is blocked by governance policy."
            ),
            missing_requirements=missing,
            consequences=[
                "Generated remediation variants remain session-local until validated.",
                "Policy limits override optimization when cost or scope boundaries are crossed.",
            ],
        )

    def estimate_worker_token_usage(self, worker_executions: list[object]) -> int:
        total_chars = 0
        for execution in worker_executions:
            stdout = getattr(execution, "stdout", "") or ""
            stderr = getattr(execution, "stderr", "") or ""
            summary = getattr(execution, "summary", "") or ""
            total_chars += len(stdout) + len(stderr) + len(summary)
        return max(0, total_chars // 4)

    def _path_allowed(self, session_dir: Path, target_path: Path, allowed_scopes: list[str]) -> bool:
        normalized = str(target_path.resolve())
        runtime_prefix = str((session_dir / "runtime").resolve())
        knowledge_prefix = str((self.root / "knowledge").resolve())
        for scope in allowed_scopes:
            if scope == "knowledge" and normalized.startswith(knowledge_prefix):
                return True
            if scope == "devices/*/runtime" and normalized.startswith(runtime_prefix):
                return True
            if scope.endswith("*"):
                prefix = scope[:-1]
                if normalized.startswith(str((self.root / prefix).resolve())):
                    return True
        return False

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

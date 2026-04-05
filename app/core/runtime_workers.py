from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.core.models import TaskRisk, WorkerRole, WorkerRouteDecision, WorkerTier


@dataclass
class WorkerTask:
    task_type: str
    summary: str
    risk: TaskRisk = TaskRisk.LOW
    needs_repo_edit: bool = False
    architecture_level: bool = False
    repetitive: bool = False
    local_retry_count: int = 0


@dataclass
class WorkerAdapter:
    role: WorkerRole
    tier: WorkerTier
    label: str
    command: list[str]
    purpose: str
    available: bool = False
    fallback_role: WorkerRole | None = None
    helper_commands: list[str] = field(default_factory=list)

    def command_hint(self) -> str:
        return " ".join(self.command)


@dataclass
class WorkerRegistry:
    root: Path
    adapters: dict[WorkerRole, WorkerAdapter] = field(default_factory=dict)

    def discover(self) -> "WorkerRegistry":
        candidates = [
            WorkerAdapter(
                role=WorkerRole.FRONTIER_ARCHITECT,
                tier=WorkerTier.FRONTIER,
                label="Frontier architect path",
                command=["codex"],
                purpose="Major architecture changes, high-risk planning, and escalation work.",
            ),
            WorkerAdapter(
                role=WorkerRole.LOCAL_GENERAL,
                tier=WorkerTier.LOCAL,
                label="Goose local worker",
                command=["goose"],
                purpose="General autonomous execution, remediation loops, and local tool use.",
                fallback_role=WorkerRole.FRONTIER_ARCHITECT,
                helper_commands=["ollama run qwen3:8b"],
            ),
            WorkerAdapter(
                role=WorkerRole.LOCAL_EDITOR,
                tier=WorkerTier.LOCAL,
                label="Aider local editor",
                command=["aider"],
                purpose="Repo-aware edits, patch creation, and test-fix loops.",
                fallback_role=WorkerRole.FRONTIER_ARCHITECT,
                helper_commands=["ollama run qwen3:8b"],
            ),
            WorkerAdapter(
                role=WorkerRole.POLICY_GUARD,
                tier=WorkerTier.DETERMINISTIC,
                label="Deterministic policy guard",
                command=["internal-policy-guard"],
                purpose="Approvals, hard stops, and destructive-action checks.",
            ),
        ]
        for adapter in candidates:
            adapter.available = adapter.command[0] == "internal-policy-guard" or shutil.which(adapter.command[0]) is not None
            self.adapters[adapter.role] = adapter
        return self

    def get(self, role: WorkerRole) -> WorkerAdapter:
        adapter = self.adapters.get(role)
        if adapter is None:
            raise KeyError(f"Worker adapter for {role.value} is not registered")
        return adapter

    def inventory(self) -> list[dict[str, object]]:
        return [
            {
                "role": adapter.role.value,
                "tier": adapter.tier.value,
                "label": adapter.label,
                "purpose": adapter.purpose,
                "command_hint": adapter.command_hint(),
                "available": adapter.available,
                "fallback_role": adapter.fallback_role.value if adapter.fallback_role else None,
                "helper_commands": adapter.helper_commands,
            }
            for adapter in self.adapters.values()
        ]


class WorkerRouter:
    def __init__(self, registry: WorkerRegistry) -> None:
        self.registry = registry

    def route(self, task: WorkerTask) -> WorkerRouteDecision:
        if task.architecture_level or task.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL}:
            return self._decision(
                task,
                WorkerRole.FRONTIER_ARCHITECT,
                "High-risk or architecture-level work must escalate to the frontier architect path.",
                [
                    "confidence is low",
                    "task affects irreversible install planning",
                    "local retries are exhausted",
                ],
            )

        if task.needs_repo_edit:
            return self._decision(
                task,
                WorkerRole.LOCAL_EDITOR,
                "Repo-aware code changes should default to the local editor worker.",
                [
                    "edit loop stalls repeatedly",
                    "patches touch safety-critical install logic",
                    "requested change expands into architecture work",
                ],
            )

        if task.repetitive:
            return self._decision(
                task,
                WorkerRole.LOCAL_GENERAL,
                "Cheap repetitive reasoning and local execution should stay on the local general worker.",
                [
                    "worker cannot validate its own output",
                    "task drifts into security-critical judgment",
                ],
            )

        if task.local_retry_count >= 2:
            return self._decision(
                task,
                WorkerRole.FRONTIER_ARCHITECT,
                "The local retry budget is exhausted, so the task escalates to the frontier path.",
                [
                    "route back to local only after a narrower remediation plan exists",
                ],
            )

        return self._decision(
            task,
            WorkerRole.LOCAL_GENERAL,
            "Default to the cheapest suitable worker for general runtime execution.",
            [
                "worker stalls on the same blocker",
                "result quality is too low for the risk level",
            ],
        )

    def _decision(
        self,
        task: WorkerTask,
        role: WorkerRole,
        rationale: str,
        escalation_triggers: list[str],
    ) -> WorkerRouteDecision:
        adapter = self.registry.get(role)
        fallback = adapter.fallback_role
        if not adapter.available and fallback is not None:
            adapter = self.registry.get(fallback)
            rationale = f"{rationale} Primary adapter is unavailable, so ForgeOS falls back to {adapter.role.value}."
        return WorkerRouteDecision(
            task_type=task.task_type,
            selected_worker=adapter.role,
            selected_tier=adapter.tier,
            rationale=rationale,
            command_hint=adapter.command_hint(),
            fallback_worker=fallback,
            escalation_triggers=escalation_triggers,
        )

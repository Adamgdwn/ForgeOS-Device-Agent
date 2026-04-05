from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.host_capabilities import discover_host_capabilities
from app.core.models import (
    RetryTelemetry,
    TaskRisk,
    WorkerExecution,
    WorkerRole,
    WorkerRouteDecision,
    WorkerTier,
    utc_now,
)


@dataclass
class WorkerTask:
    task_type: str
    summary: str
    prompt: str = ""
    risk: TaskRisk = TaskRisk.LOW
    needs_repo_edit: bool = False
    architecture_level: bool = False
    repetitive: bool = False
    local_retry_count: int = 0
    retry_budget: int = 1
    context: dict[str, Any] = field(default_factory=dict)
    target_files: list[str] = field(default_factory=list)
    invocation_override: list[str] | None = None


@dataclass
class WorkerAdapter:
    role: WorkerRole
    tier: WorkerTier
    label: str
    executable: str
    purpose: str
    available: bool = False
    fallback_role: WorkerRole | None = None

    def adapter_name(self) -> str:
        return self.label.lower().replace(" ", "_")


class OllamaAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.executable = os.environ.get("FORGEOS_OLLAMA_EXECUTABLE", "ollama")
        self.model = os.environ.get("FORGEOS_OLLAMA_MODEL", "qwen3:8b")
        self.available = shutil.which(self.executable) is not None

    def build_command(self, task: WorkerTask) -> list[str]:
        if task.invocation_override:
            return list(task.invocation_override)
        return [
            self.executable,
            "run",
            self.model,
            task.prompt or task.summary,
            "--format",
            "json",
            "--hidethinking",
        ]


class GooseAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.executable = os.environ.get("FORGEOS_GOOSE_EXECUTABLE", "goose")
        self.provider = os.environ.get("FORGEOS_GOOSE_PROVIDER", "ollama")
        self.model = os.environ.get("FORGEOS_GOOSE_MODEL", "qwen3:8b")
        self.available = shutil.which(self.executable) is not None

    def build_command(self, task: WorkerTask) -> list[str]:
        if task.invocation_override:
            return list(task.invocation_override)
        return [
            self.executable,
            "run",
            "--text",
            task.prompt or task.summary,
            "--no-session",
            "--quiet",
            "--output-format",
            "json",
            "--provider",
            self.provider,
            "--model",
            self.model,
        ]


class AiderAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.executable = os.environ.get("FORGEOS_AIDER_EXECUTABLE", "aider")
        self.model = os.environ.get("FORGEOS_AIDER_MODEL", "")
        self.available = shutil.which(self.executable) is not None

    def build_command(self, task: WorkerTask, session_dir: Path) -> list[str]:
        if task.invocation_override:
            return list(task.invocation_override)
        command = [
            self.executable,
            "--message",
            task.prompt or task.summary,
            "--yes-always",
            "--no-auto-commits",
            "--no-pretty",
            "--no-stream",
            "--map-tokens",
            "0",
            "--no-show-release-notes",
            "--no-check-update",
            "--input-history-file",
            str(session_dir / "runtime" / ".aider.input.history"),
            "--chat-history-file",
            str(session_dir / "runtime" / ".aider.chat.history.md"),
            "--llm-history-file",
            str(session_dir / "runtime" / ".aider.llm.history.log"),
        ]
        if self.model:
            command.extend(["--model", self.model])
        for target in task.target_files:
            command.extend(["--file", target])
        return command


@dataclass
class WorkerRegistry:
    root: Path
    adapters: dict[WorkerRole, WorkerAdapter] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)

    def discover(self) -> "WorkerRegistry":
        capabilities = discover_host_capabilities(self.root)
        self.capabilities = capabilities
        candidates = [
            WorkerAdapter(
                role=WorkerRole.FRONTIER_ARCHITECT,
                tier=WorkerTier.FRONTIER,
                label="Frontier architect path",
                executable=os.environ.get("FORGEOS_FRONTIER_EXECUTABLE", "codex"),
                purpose="Major architecture changes, high-risk planning, and escalation work.",
            ),
            WorkerAdapter(
                role=WorkerRole.LOCAL_GENERAL,
                tier=WorkerTier.LOCAL,
                label="Goose local worker",
                executable=os.environ.get("FORGEOS_GOOSE_EXECUTABLE", "goose"),
                purpose="General autonomous execution, remediation loops, and local tool use.",
                fallback_role=WorkerRole.FRONTIER_ARCHITECT,
            ),
            WorkerAdapter(
                role=WorkerRole.LOCAL_EDITOR,
                tier=WorkerTier.LOCAL,
                label="Aider local editor",
                executable=os.environ.get("FORGEOS_AIDER_EXECUTABLE", "aider"),
                purpose="Repo-aware edits, patch creation, and test-fix loops.",
                fallback_role=WorkerRole.FRONTIER_ARCHITECT,
            ),
            WorkerAdapter(
                role=WorkerRole.POLICY_GUARD,
                tier=WorkerTier.DETERMINISTIC,
                label="Deterministic policy guard",
                executable="internal-policy-guard",
                purpose="Approvals, hard stops, and destructive-action checks.",
            ),
        ]
        for adapter in candidates:
            if adapter.role == WorkerRole.LOCAL_GENERAL:
                adapter.available = bool(capabilities.get("goose_ready"))
            elif adapter.role == WorkerRole.LOCAL_EDITOR:
                adapter.available = bool(capabilities.get("aider_ready"))
            elif adapter.role == WorkerRole.FRONTIER_ARCHITECT:
                adapter.available = bool(capabilities.get("codex_available"))
            else:
                adapter.available = True
            self.adapters[adapter.role] = adapter
        return self

    def get(self, role: WorkerRole) -> WorkerAdapter:
        adapter = self.adapters.get(role)
        if adapter is None:
            raise KeyError(f"Worker adapter for {role.value} is not registered")
        return adapter

    def inventory(self) -> list[dict[str, object]]:
        tool_map = {record["executable"]: record for record in self.capabilities.get("tools", [])}
        reason_keys = {
            WorkerRole.LOCAL_GENERAL: "goose",
            WorkerRole.LOCAL_EDITOR: "aider",
            WorkerRole.FRONTIER_ARCHITECT: "codex",
            WorkerRole.POLICY_GUARD: "policy_guard",
        }
        return [
            {
                "role": adapter.role.value,
                "tier": adapter.tier.value,
                "label": adapter.label,
                "purpose": adapter.purpose,
                "adapter_name": adapter.adapter_name(),
                "executable": adapter.executable,
                "available": adapter.available,
                "fallback_role": adapter.fallback_role.value if adapter.fallback_role else None,
                "version": tool_map.get(adapter.executable, {}).get("version", ""),
                "readiness_reason": self.capabilities.get("reasons", {}).get(reason_keys[adapter.role], ""),
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
            adapter_name=adapter.adapter_name(),
            fallback_worker=fallback,
            escalation_triggers=escalation_triggers,
        )


class WorkerRuntime:
    def __init__(self, root: Path, registry: WorkerRegistry) -> None:
        self.root = root
        self.registry = registry
        self.capabilities = discover_host_capabilities(root)
        self.ollama = OllamaAdapter(root)
        self.goose = GooseAdapter(root)
        self.aider = AiderAdapter(root)
        self.ollama.available = bool(self.capabilities.get("ollama_model_available"))
        self.goose.available = bool(self.capabilities.get("goose_ready"))
        self.aider.available = bool(self.capabilities.get("aider_ready"))

    def execute(self, route: WorkerRouteDecision, task: WorkerTask, session_dir: Path) -> WorkerExecution:
        self._write_adapter_health(session_dir)
        if route.selected_worker == WorkerRole.POLICY_GUARD:
            execution = WorkerExecution(
                worker=route.selected_worker.value,
                adapter_name=route.adapter_name,
                task_type=task.task_type,
                status="deterministic",
                summary="Task stays inside deterministic application logic.",
                confidence=0.99,
                escalation_triggers=[],
            )
            return self._write_transcript(session_dir, execution, {"task": task.summary})

        if route.selected_worker == WorkerRole.LOCAL_GENERAL:
            return self._run_local_general(route, task, session_dir)
        if route.selected_worker == WorkerRole.LOCAL_EDITOR:
            return self._run_adapter(
                worker=route.selected_worker,
                adapter_name=route.adapter_name,
                task=task,
                session_dir=session_dir,
                command=self.aider.build_command(task, session_dir),
                env={},
                escalation_triggers=route.escalation_triggers,
            )

        execution = WorkerExecution(
            worker=route.selected_worker.value,
            adapter_name=route.adapter_name,
            task_type=task.task_type,
            status="escalated",
            summary="ForgeOS recorded the escalation path for this task rather than running it locally.",
            confidence=0.2,
            escalation_triggers=route.escalation_triggers,
            telemetry=RetryTelemetry(attempts=0, retry_budget=task.retry_budget, exhausted=False),
        )
        return self._write_transcript(session_dir, execution, {"task": task.summary})

    def _run_local_general(
        self,
        route: WorkerRouteDecision,
        task: WorkerTask,
        session_dir: Path,
    ) -> WorkerExecution:
        if task.invocation_override:
            return self._run_adapter(
                worker=route.selected_worker,
                adapter_name=route.adapter_name,
                task=task,
                session_dir=session_dir,
                command=list(task.invocation_override),
                env={},
                escalation_triggers=route.escalation_triggers,
            )
        helper_first = task.repetitive or task.risk == TaskRisk.LOW
        if helper_first and self.ollama.available:
            helper = self._run_adapter(
                worker=route.selected_worker,
                adapter_name="ollama_qwen_local_helper",
                task=task,
                session_dir=session_dir,
                command=self.ollama.build_command(task),
                env={},
                escalation_triggers=route.escalation_triggers,
            )
            if helper.confidence >= 0.55 and helper.status == "completed":
                return helper

        if self.goose.available:
            return self._run_adapter(
                worker=route.selected_worker,
                adapter_name=route.adapter_name,
                task=task,
                session_dir=session_dir,
                command=self.goose.build_command(task),
                env={},
                escalation_triggers=route.escalation_triggers,
            )

        if self.ollama.available:
            fallback = self._run_adapter(
                worker=route.selected_worker,
                adapter_name="ollama_qwen_local_helper",
                task=task,
                session_dir=session_dir,
                command=self.ollama.build_command(task),
                env={},
                escalation_triggers=route.escalation_triggers,
            )
            fallback.summary = "Goose was unavailable, so ForgeOS used the Ollama local helper as the execution path."
            return fallback

        execution = WorkerExecution(
            worker=route.selected_worker.value,
            adapter_name=route.adapter_name,
            task_type=task.task_type,
            status="unavailable",
            summary="Neither Goose nor the Ollama local helper was available for this local-general task.",
            confidence=0.0,
            escalation_triggers=route.escalation_triggers + ["local worker executable unavailable"],
            telemetry=RetryTelemetry(attempts=0, retry_budget=task.retry_budget, exhausted=False),
        )
        return self._write_transcript(session_dir, execution, {"task": task.summary})

    def _run_adapter(
        self,
        worker: WorkerRole,
        adapter_name: str,
        task: WorkerTask,
        session_dir: Path,
        command: list[str],
        env: dict[str, str],
        escalation_triggers: list[str],
    ) -> WorkerExecution:
        attempts = 0
        outputs: list[str] = []
        stderr_samples: list[str] = []
        durations_ms: list[int] = []
        last_exit: int | None = None
        last_stdout = ""
        last_stderr = ""
        last_structured: dict[str, Any] = {}

        while attempts < max(1, task.retry_budget):
            attempts += 1
            started = time.monotonic()
            completed = subprocess.run(
                command,
                cwd=session_dir,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, **env},
            )
            durations_ms.append(int((time.monotonic() - started) * 1000))
            last_exit = completed.returncode
            last_stdout = completed.stdout.strip()
            last_stderr = completed.stderr.strip()
            outputs.append(last_stdout)
            stderr_samples.append(last_stderr)
            parsed = self._parse_output(adapter_name, last_stdout, last_stderr)
            if parsed:
                last_structured = parsed
            if completed.returncode == 0 and last_stdout:
                break

        repeated_failure = len(set(outputs)) == 1 and attempts > 1 and (last_exit or 0) != 0
        telemetry = RetryTelemetry(
            attempts=attempts,
            retry_budget=max(1, task.retry_budget),
            repeated_failure=repeated_failure,
            exhausted=attempts >= max(1, task.retry_budget) and (last_exit or 0) != 0,
            last_error=last_stderr,
            durations_ms=durations_ms,
        )
        confidence = self._score_confidence(last_exit, last_stdout, last_stderr, last_structured, telemetry)
        triggers = list(escalation_triggers)
        if last_exit not in {0, None}:
            triggers.append("worker exited non-zero")
        if confidence < 0.45:
            triggers.append("worker confidence fell below acceptable threshold")
        if telemetry.exhausted:
            triggers.append("retry budget exhausted")
        if telemetry.repeated_failure:
            triggers.append("worker repeated the same failing output")

        execution = WorkerExecution(
            worker=worker.value,
            adapter_name=adapter_name,
            task_type=task.task_type,
            status="completed" if last_exit == 0 else "failed",
            summary=self._build_summary(task, last_exit, confidence, telemetry),
            command=command,
            stdout=last_stdout,
            stderr=last_stderr,
            exit_code=last_exit,
            confidence=confidence,
            escalation_triggers=triggers,
            telemetry=telemetry,
            structured_output=last_structured,
        )
        return self._write_transcript(
            session_dir,
            execution,
            {"task": task.summary, "prompt": task.prompt, "context": task.context},
        )

    def _parse_output(self, adapter_name: str, stdout: str, stderr: str) -> dict[str, Any]:
        if not stdout:
            return {"stderr_summary": stderr[:400]} if stderr else {}
        try:
            return json.loads(stdout)
        except Exception:
            pass
        if adapter_name.startswith("ollama"):
            lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            if not lines:
                return {}
            parsed_lines = []
            for line in lines[:20]:
                try:
                    parsed_lines.append(json.loads(line))
                except Exception:
                    parsed_lines.append({"text": line})
            return {"responses": parsed_lines}
        if adapter_name == "goose_local_worker":
            return {"response_text": stdout[:2000]}
        if adapter_name == "aider_local_editor":
            changed_files = []
            for line in stdout.splitlines():
                if line.startswith("Applied edit to") or line.startswith("Added "):
                    changed_files.append(line)
            return {"response_text": stdout[:2000], "change_hints": changed_files}
        return {"response_text": stdout[:2000]}

    def _score_confidence(
        self,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        structured_output: dict[str, Any],
        telemetry: RetryTelemetry,
    ) -> float:
        score = 0.1
        if exit_code == 0:
            score += 0.45
        if stdout:
            score += 0.2
        if structured_output:
            score += 0.15
        if stderr:
            score -= 0.1
        if telemetry.repeated_failure:
            score -= 0.15
        if telemetry.exhausted and exit_code != 0:
            score -= 0.25
        return max(0.0, min(0.99, round(score, 2)))

    def _build_summary(
        self,
        task: WorkerTask,
        exit_code: int | None,
        confidence: float,
        telemetry: RetryTelemetry,
    ) -> str:
        if exit_code == 0:
            return f"Executed `{task.task_type}` with confidence {confidence:.2f} after {telemetry.attempts} attempt(s)."
        return f"`{task.task_type}` failed after {telemetry.attempts} attempt(s) with confidence {confidence:.2f}."

    def _write_transcript(
        self,
        session_dir: Path,
        execution: WorkerExecution,
        extra: dict[str, Any],
    ) -> WorkerExecution:
        transcripts_dir = session_dir / "runtime" / "workers"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        safe_task = execution.task_type.replace("/", "-").replace(" ", "_")
        transcript_path = transcripts_dir / f"{safe_task}-{int(time.time() * 1000)}.json"
        transcript = {
            "generated_at": utc_now(),
            "worker": execution.worker,
            "adapter_name": execution.adapter_name,
            "task_type": execution.task_type,
            "status": execution.status,
            "summary": execution.summary,
            "command": execution.command,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "exit_code": execution.exit_code,
            "confidence": execution.confidence,
            "escalation_triggers": execution.escalation_triggers,
            "telemetry": {
                "attempts": execution.telemetry.attempts,
                "retry_budget": execution.telemetry.retry_budget,
                "repeated_failure": execution.telemetry.repeated_failure,
                "exhausted": execution.telemetry.exhausted,
                "last_error": execution.telemetry.last_error,
                "durations_ms": execution.telemetry.durations_ms,
            },
            "structured_output": execution.structured_output,
            "task": extra,
        }
        transcript_path.write_text(json.dumps(transcript, indent=2))
        execution.transcript_path = str(transcript_path)
        return execution

    def _write_adapter_health(self, session_dir: Path) -> None:
        runtime_dir = session_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        health_path = runtime_dir / "adapter-health.json"
        health_path.write_text(json.dumps(self.capabilities, indent=2))

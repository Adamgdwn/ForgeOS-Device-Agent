from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Mapping


DEFAULT_FAST_MODEL = "qwen3:8b"
DEFAULT_REASONING_MODEL = "gemma4:latest"
DEFAULT_RESEARCH_MODEL = "deepseek-r1:14b"
DEFAULT_FRONTIER_MODEL = "gpt-oss:20b"
DEFAULT_VISION_MODEL = "qwen3-vl:8b"
DEFAULT_CODING_MODEL = "qwen2.5-coder:14b"
DEFAULT_LARGE_CODING_MODEL = "qwen3-coder:30b"


@dataclass(frozen=True)
class ModelSelection:
    role: str
    model: str
    provider: str = "ollama"
    reason: str = ""
    requested_model: str | None = None
    available: bool = False
    source: str = "default"

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "available": self.available,
            "requested_model": self.requested_model,
            "source": self.source,
            "reason": self.reason,
        }

    def aider_model(self) -> str:
        if self.model.startswith(("ollama/", "ollama_chat/", "openai/", "anthropic/")):
            return self.model
        return f"ollama_chat/{self.model}"


@dataclass
class ModelRouter:
    """Select local models by job shape instead of using one hardcoded default."""

    available_models: set[str] = field(default_factory=set)
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)

    @classmethod
    def discover(cls, env: Mapping[str, str] | None = None) -> "ModelRouter":
        env_map = env or os.environ
        executable = env_map.get("FORGEOS_OLLAMA_EXECUTABLE", "ollama")
        if not shutil.which(executable):
            return cls(set(), env_map)
        try:
            completed = subprocess.run(
                [executable, "list"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except Exception:  # noqa: BLE001
            return cls(set(), env_map)
        if completed.returncode != 0:
            return cls(set(), env_map)
        return cls.from_ollama_list(completed.stdout, env_map)

    @classmethod
    def from_ollama_list(
        cls,
        output: str,
        env: Mapping[str, str] | None = None,
    ) -> "ModelRouter":
        models: set[str] = set()
        for line in output.splitlines():
            parts = line.split()
            if not parts or parts[0].lower() == "name":
                continue
            models.add(parts[0])
        return cls(models, env or os.environ)

    def base_model(self) -> str:
        return self.env.get("FORGEOS_OLLAMA_MODEL", DEFAULT_REASONING_MODEL)

    def select(
        self,
        role: str,
        *,
        task_type: str = "",
        risk: str = "low",
        needs_repo_edit: bool = False,
        architecture_level: bool = False,
        repetitive: bool = False,
    ) -> ModelSelection:
        normalized_role = role or self.role_for_task(
            task_type=task_type,
            risk=risk,
            needs_repo_edit=needs_repo_edit,
            architecture_level=architecture_level,
            repetitive=repetitive,
        )
        candidates = self._candidates(normalized_role)
        requested = candidates[0] if candidates else self.base_model()
        for model, source in candidates:
            if self._is_available(model):
                return ModelSelection(
                    role=normalized_role,
                    model=model,
                    provider=self._provider_for(model, source),
                    requested_model=requested[0],
                    available=True,
                    source=source,
                    reason=self._reason(normalized_role, model, source, requested[0]),
                )
        fallback = requested[0] if requested else self.base_model()
        return ModelSelection(
            role=normalized_role,
            model=fallback,
            provider=self._provider_for(fallback, requested[1] if requested else "default"),
            requested_model=requested[0] if requested else None,
            available=False,
            source=requested[1] if requested else "default",
            reason=(
                f"No installed Ollama model matched the {normalized_role} route; "
                f"ForgeOS will attempt `{fallback}` and report adapter availability separately."
            ),
        )

    def select_for_task(
        self,
        *,
        task_type: str,
        risk: str,
        needs_repo_edit: bool = False,
        architecture_level: bool = False,
        repetitive: bool = False,
    ) -> ModelSelection:
        role = self.role_for_task(
            task_type=task_type,
            risk=risk,
            needs_repo_edit=needs_repo_edit,
            architecture_level=architecture_level,
            repetitive=repetitive,
        )
        return self.select(
            role,
            task_type=task_type,
            risk=risk,
            needs_repo_edit=needs_repo_edit,
            architecture_level=architecture_level,
            repetitive=repetitive,
        )

    def configured_routes(self) -> dict[str, dict[str, Any]]:
        return {
            role: self.select(role).as_dict()
            for role in [
                "fast_triage",
                "general_reasoning",
                "research",
                "coding",
                "frontier",
                "visual_inspection",
            ]
        }

    @staticmethod
    def role_for_task(
        *,
        task_type: str,
        risk: str,
        needs_repo_edit: bool = False,
        architecture_level: bool = False,
        repetitive: bool = False,
    ) -> str:
        risk_value = str(getattr(risk, "value", risk)).lower()
        task = task_type.lower()
        if needs_repo_edit:
            return "coding"
        if any(marker in task for marker in ("vision", "visual", "screenshot", "ocr", "image", "ui_inspection")):
            return "visual_inspection"
        if architecture_level or risk_value in {"high", "critical"}:
            return "frontier"
        if "research" in task or "source" in task or "firmware" in task or "blocker" in task:
            return "research"
        if repetitive or risk_value == "low":
            return "fast_triage"
        return "general_reasoning"

    def _candidates(self, role: str) -> list[tuple[str, str]]:
        base = self.base_model()
        role_env = {
            "fast_triage": "FORGEOS_FAST_MODEL",
            "general_reasoning": "FORGEOS_REASONING_MODEL",
            "research": "FORGEOS_RESEARCH_MODEL",
            "coding": "FORGEOS_CODING_MODEL",
            "frontier": "FORGEOS_FRONTIER_MODEL",
            "visual_inspection": "FORGEOS_VISION_MODEL",
        }
        candidates: list[tuple[str, str]] = []
        env_key = role_env.get(role)
        if env_key and self.env.get(env_key):
            candidates.append((self.env[env_key], env_key))
        if role == "fast_triage":
            candidates.append((DEFAULT_FAST_MODEL, "default_fast"))
        elif role == "research":
            candidates.append((DEFAULT_RESEARCH_MODEL, "default_research"))
            candidates.append((DEFAULT_FRONTIER_MODEL, "default_frontier"))
        elif role == "frontier":
            candidates.append((DEFAULT_FRONTIER_MODEL, "default_frontier"))
            candidates.append((DEFAULT_RESEARCH_MODEL, "default_research"))
        elif role == "visual_inspection":
            candidates.append((DEFAULT_VISION_MODEL, "default_vision"))
        elif role == "coding":
            if self.env.get("FORGEOS_AIDER_MODEL"):
                candidates.append((self.env["FORGEOS_AIDER_MODEL"], "FORGEOS_AIDER_MODEL"))
            candidates.append((DEFAULT_CODING_MODEL, "default_coding"))
            candidates.append((DEFAULT_LARGE_CODING_MODEL, "default_large_coding"))
        if role == "frontier" and self.env.get("FORGEOS_REASONING_MODEL"):
            candidates.append((self.env["FORGEOS_REASONING_MODEL"], "FORGEOS_REASONING_MODEL"))
        candidates.append((base, "FORGEOS_OLLAMA_MODEL" if self.env.get("FORGEOS_OLLAMA_MODEL") else "default_reasoning"))
        return self._dedupe(candidates)

    def _is_available(self, model: str) -> bool:
        if model.startswith(("openai/", "anthropic/")):
            return True
        plain = self._plain_model_name(model)
        return bool(self.available_models) and plain in self.available_models

    @staticmethod
    def _provider_for(model: str, source: str) -> str:
        if source == "FORGEOS_AIDER_MODEL":
            return "aider"
        if model.startswith("openai/"):
            return "openai"
        if model.startswith("anthropic/"):
            return "anthropic"
        return "ollama"

    @staticmethod
    def _plain_model_name(model: str) -> str:
        for prefix in ("ollama_chat/", "ollama/"):
            if model.startswith(prefix):
                return model[len(prefix):]
        return model

    @staticmethod
    def _dedupe(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
        seen: set[str] = set()
        deduped: list[tuple[str, str]] = []
        for model, source in candidates:
            if not model or model in seen:
                continue
            seen.add(model)
            deduped.append((model, source))
        return deduped

    @staticmethod
    def _reason(role: str, model: str, source: str, requested: str) -> str:
        if source.startswith("FORGEOS_"):
            return f"`{model}` was selected for {role} from `{source}`."
        if model != requested:
            return f"`{requested}` was unavailable, so `{model}` was selected for {role}."
        return f"`{model}` is the default installed model for {role}."

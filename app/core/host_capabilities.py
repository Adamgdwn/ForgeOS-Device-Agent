from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _safe_run(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


def discover_host_capabilities(root: Path) -> dict[str, Any]:
    ollama_exec = os.environ.get("FORGEOS_OLLAMA_EXECUTABLE", "ollama")
    goose_exec = os.environ.get("FORGEOS_GOOSE_EXECUTABLE", "goose")
    aider_exec = os.environ.get("FORGEOS_AIDER_EXECUTABLE", "aider")
    codex_exec = os.environ.get("FORGEOS_FRONTIER_EXECUTABLE", "codex")
    ollama_model = os.environ.get("FORGEOS_OLLAMA_MODEL", "qwen3:8b")
    aider_model = os.environ.get("FORGEOS_AIDER_MODEL", "")

    tool_records = []
    for name, executable, version_args in [
        ("codex", codex_exec, ["--version"]),
        ("goose", goose_exec, ["--version"]),
        ("aider", aider_exec, ["--version"]),
        ("ollama", ollama_exec, ["--version"]),
    ]:
        path = shutil.which(executable)
        version = _safe_run([executable, *version_args]) if path else {"ok": False, "stdout": "", "stderr": "not installed"}
        tool_records.append(
            {
                "name": name,
                "executable": executable,
                "path": path,
                "available": bool(path),
                "version": version.get("stdout", ""),
                "error": version.get("stderr", ""),
            }
        )

    ollama_models = _safe_run([ollama_exec, "list"]) if shutil.which(ollama_exec) else {"ok": False, "stdout": "", "stderr": "ollama unavailable"}
    model_available = ollama_model in ollama_models.get("stdout", "")

    aider_ready = bool(shutil.which(aider_exec)) and bool(
        aider_model
        or os.environ.get("AIDER_MODEL")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
    )
    goose_ready = bool(shutil.which(goose_exec)) and (bool(shutil.which(ollama_exec)) and model_available)

    return {
        "workspace_root": str(root),
        "local_model": ollama_model,
        "tools": tool_records,
        "goose_available": bool(shutil.which(goose_exec)),
        "goose_ready": goose_ready,
        "aider_available": bool(shutil.which(aider_exec)),
        "aider_ready": aider_ready,
        "ollama_available": bool(shutil.which(ollama_exec)),
        "ollama_model_available": model_available,
        "ollama_models_output": ollama_models.get("stdout", ""),
        "codex_available": bool(shutil.which(codex_exec)),
        "reasons": {
            "goose": (
                "ready"
                if goose_ready
                else "Goose requires both the CLI and a ready local Ollama model."
            ),
            "aider": (
                "ready"
                if aider_ready
                else "Aider needs the CLI plus a configured model/provider."
            ),
            "ollama": (
                "ready"
                if model_available
                else f"Ollama is missing the configured model `{ollama_model}`."
            ),
            "codex": "ready" if bool(shutil.which(codex_exec)) else "Codex CLI is unavailable on this host.",
            "policy_guard": "ready",
        },
    }

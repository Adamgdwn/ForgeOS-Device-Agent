from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.integrations import adb, fastboot


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
    ollama_api_base = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")
    emulator_exec = shutil.which("emulator")
    avdmanager_exec = shutil.which("avdmanager")
    sdkmanager_exec = shutil.which("sdkmanager")

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
        or (bool(shutil.which(ollama_exec)) and model_available)
    )
    goose_ready = bool(shutil.which(goose_exec)) and (bool(shutil.which(ollama_exec)) and model_available)
    emulator_list = _safe_run([emulator_exec, "-list-avds"]) if emulator_exec else {"ok": False, "stdout": "", "stderr": "emulator unavailable"}
    avd_names = [line.strip() for line in emulator_list.get("stdout", "").splitlines() if line.strip()]

    return {
        "workspace_root": str(root),
        "local_model": ollama_model,
        "ollama_api_base": ollama_api_base,
        "tools": tool_records,
        "adb_available": adb.adb_available(),
        "fastboot_available": fastboot.fastboot_available(),
        "goose_available": bool(shutil.which(goose_exec)),
        "goose_ready": goose_ready,
        "aider_available": bool(shutil.which(aider_exec)),
        "aider_ready": aider_ready,
        "ollama_available": bool(shutil.which(ollama_exec)),
        "ollama_model_available": model_available,
        "ollama_models_output": ollama_models.get("stdout", ""),
        "codex_available": bool(shutil.which(codex_exec)),
        "emulator_available": bool(emulator_exec),
        "avdmanager_available": bool(avdmanager_exec),
        "sdkmanager_available": bool(sdkmanager_exec),
        "available_avds": avd_names,
        "reasons": {
            "goose": (
                "ready"
                if goose_ready
                else "Goose requires both the CLI and a ready local Ollama model."
            ),
            "aider": (
                "ready"
                if aider_ready
                else "Aider needs the CLI plus either a configured provider or a ready local Ollama model."
            ),
            "ollama": (
                "ready"
                if model_available
                else f"Ollama is missing the configured model `{ollama_model}`."
            ),
            "codex": "ready" if bool(shutil.which(codex_exec)) else "Codex CLI is unavailable on this host.",
            "policy_guard": "ready",
            "emulator": (
                "ready"
                if emulator_exec and avd_names
                else "Android emulator or AVD definitions are unavailable on this host."
            ),
        },
    }

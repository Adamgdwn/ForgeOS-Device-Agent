from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def code_available() -> bool:
    return shutil.which("code") is not None


def open_in_vscode(target_path: Path, new_window: bool = False) -> dict[str, object]:
    if not code_available():
        return {
            "opened": False,
            "reason": "VS Code CLI `code` not found",
            "target": str(target_path),
        }
    command = ["code", str(target_path)]
    if new_window:
        command.insert(1, "--new-window")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "opened": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "target": str(target_path),
    }

from __future__ import annotations

from pathlib import Path

from app.integrations.vscode import open_in_vscode
from app.tools.base import BaseTool


class VSCodeOpenerTool(BaseTool):
    name = "vscode_opener"
    input_schema = {"target_path": "string", "new_window": "boolean"}
    output_schema = {"opened": "boolean", "target": "string"}

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        target = Path(str(payload["target_path"]))
        return open_in_vscode(target, bool(payload.get("new_window", False)))

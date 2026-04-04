from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class BootloaderManagerTool(BaseTool):
    name = "bootloader_manager"
    input_schema = {"device": "object", "action": "string"}
    output_schema = {"status": "string"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {"status": "stub", "action": payload.get("action", "inspect")}

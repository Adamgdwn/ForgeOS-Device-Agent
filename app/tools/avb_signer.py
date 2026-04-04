from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool


class AVBSignerTool(BaseTool):
    name = "avb_signer"
    input_schema = {"artifacts": "array"}
    output_schema = {"signed_artifacts": "array"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        return {"signed_artifacts": [], "status": "stub"}

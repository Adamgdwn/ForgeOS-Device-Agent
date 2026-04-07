from __future__ import annotations

import shutil
from pathlib import Path

from app.tools.base import BaseTool


class AVBSignerTool(BaseTool):
    name = "avb_signer"
    input_schema = {"artifacts": "array"}
    output_schema = {"signed_artifacts": "array"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        artifacts = [str(item) for item in payload.get("artifacts", []) if item]
        if not shutil.which("avbtool"):
            return {
                "signed_artifacts": [],
                "status": "avbtool_missing",
                "blocks": False,
                "reason": "avbtool is not available on PATH; development builds may continue unsigned.",
            }
        return {
            "signed_artifacts": artifacts,
            "status": "not_implemented",
            "blocks": True,
            "reason": "avb_signer detected avbtool but signing flow is not implemented yet.",
        }

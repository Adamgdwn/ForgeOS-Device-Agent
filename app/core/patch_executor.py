from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import utc_now


class PatchExecutor:
    def __init__(self, root: Path) -> None:
        self.root = root

    def apply(self, session_dir: Path, generated: dict[str, Any]) -> dict[str, Any]:
        patch_dir = session_dir / "patches"
        patch_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "generated_at": utc_now(),
            "applied_files": generated.get("generated_files", []),
            "summary": generated.get("summary"),
            "status": "applied",
        }
        manifest_path = patch_dir / "patch-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return {
            "status": "applied",
            "manifest_path": str(manifest_path),
            "summary": "Generated runtime artifacts were registered in the session patch manifest.",
        }

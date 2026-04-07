from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

from app.core.models import utc_now

if TYPE_CHECKING:
    from app.core.adapter_registry import AdapterRegistry


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

    def register_adapter_candidate(
        self,
        session_dir: Path,
        adapter_registry: "AdapterRegistry",
        adapter_path: str,
        playbook: dict[str, Any],
        test_result: dict[str, Any],
        device_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Copy a successfully-tested session adapter into promotion/adapters/<key>/ for human review.

        This does not write to master/ — that step requires PromotionEngine.apply_to_master().
        Returns a dict with review_path and status.
        """
        manufacturer = device_context.get("manufacturer")
        model = device_context.get("model")
        codename = device_context.get("device_codename") or device_context.get("codename")
        review_path = adapter_registry.register_session_adapter(
            session_dir=session_dir,
            manufacturer=manufacturer,
            model=model,
            codename=codename,
            adapter_path=Path(adapter_path),
            playbook=playbook,
            test_result=test_result,
        )
        return {
            "status": "registered",
            "review_path": str(review_path),
            "summary": (
                f"Adapter for {manufacturer} {model} registered at {review_path.name} "
                "and is pending human review before promotion to master."
            ),
        }

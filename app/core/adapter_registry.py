from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _slug(value: str | None) -> str:
    if not value:
        return "unknown"
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_") or "unknown"


def _adapter_key(manufacturer: str | None, model: str | None) -> str:
    return f"{_slug(manufacturer)}_{_slug(model)}"


class AdapterRegistry:
    """Tracks which OEM adapters exist in master/ and which have been generated
    but not yet promoted.

    master/integrations/oem_adapters/<key>.py   — promoted, reusable adapter
    master/playbooks/connection/<key>.json       — promoted connection playbook
    promotion/adapters/<key>/                   — session-generated, pending review
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.master_adapters_dir = root / "master" / "integrations" / "oem_adapters"
        self.master_playbooks_dir = root / "master" / "playbooks" / "connection"
        self.review_dir = root / "promotion" / "adapters"

    def has_master_adapter(self, manufacturer: str | None, model: str | None) -> bool:
        key = _adapter_key(manufacturer, model)
        return (self.master_adapters_dir / f"{key}.py").exists()

    def has_master_playbook(self, manufacturer: str | None, model: str | None) -> bool:
        key = _adapter_key(manufacturer, model)
        return (self.master_playbooks_dir / f"{key}.json").exists()

    def adapter_key(self, manufacturer: str | None, model: str | None) -> str:
        return _adapter_key(manufacturer, model)

    def get_master_adapter_path(self, manufacturer: str | None, model: str | None) -> Path:
        return self.master_adapters_dir / f"{_adapter_key(manufacturer, model)}.py"

    def get_master_playbook_path(self, manufacturer: str | None, model: str | None) -> Path:
        return self.master_playbooks_dir / f"{_adapter_key(manufacturer, model)}.json"

    def get_review_dir(self, manufacturer: str | None, model: str | None) -> Path:
        return self.review_dir / _adapter_key(manufacturer, model)

    def get_review_dir_by_key(self, key: str) -> Path:
        return self.review_dir / key

    def get_master_adapter_path_by_key(self, key: str) -> Path:
        return self.master_adapters_dir / f"{key}.py"

    def get_master_playbook_path_by_key(self, key: str) -> Path:
        return self.master_playbooks_dir / f"{key}.json"

    def list_master_adapters(self) -> list[str]:
        if not self.master_adapters_dir.exists():
            return []
        return [p.stem for p in self.master_adapters_dir.glob("*.py") if p.stem != "__init__"]

    def register_session_adapter(
        self,
        session_dir: Path,
        manufacturer: str | None,
        model: str | None,
        codename: str | None,
        adapter_path: Path,
        playbook: dict[str, Any],
        test_result: dict[str, Any],
    ) -> Path:
        """Copy a successfully-tested session adapter into the promotion review area.

        Does not write to master/ — that requires PromotionEngine.apply_to_master().
        """
        key = _adapter_key(manufacturer, model)
        review_path = self.review_dir / key
        review_path.mkdir(parents=True, exist_ok=True)

        dest_adapter = review_path / f"{key}.py"
        dest_adapter.write_text(adapter_path.read_text())

        dest_playbook = review_path / f"{key}.json"
        dest_playbook.write_text(json.dumps(playbook, indent=2))

        meta = {
            "key": key,
            "manufacturer": manufacturer,
            "model": model,
            "codename": codename,
            "source_session": session_dir.name,
            "adapter_path": str(dest_adapter),
            "playbook_path": str(dest_playbook),
            "test_result": test_result,
            "test_source": test_result.get("status", ""),
            "status": "pending_review",
        }
        meta_path = review_path / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2))
        return review_path

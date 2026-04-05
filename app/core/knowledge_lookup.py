from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.knowledge import KnowledgeEngine


class KnowledgeLookup:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.knowledge = KnowledgeEngine(root)

    def lookup(self, manufacturer: str | None, model: str | None) -> dict[str, Any]:
        family = self.knowledge.lookup_family_summary(manufacturer, model)
        return {
            "family_summary": family,
            "has_prior_knowledge": family is not None,
        }

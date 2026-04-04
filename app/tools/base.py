from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.core.models import FailureSeverity, utc_now


class ToolFailure(Exception):
    def __init__(self, message: str, severity: FailureSeverity = FailureSeverity.RECOVERABLE):
        super().__init__(message)
        self.severity = severity


class BaseTool(ABC):
    name = "base"
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    retry_limit = 1
    supports_dry_run = True

    def __init__(self, root: Path) -> None:
        self.root = root
        self.logger = logging.getLogger(self.name)
        self.audit_dir = root / "logs" / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def execute(self, payload: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
        attempt = 0
        last_error: Exception | None = None
        while attempt < self.retry_limit:
            try:
                result = self.run(payload | {"dry_run": dry_run})
                self._audit(payload, result, "ok")
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempt += 1
                self.logger.warning("Tool %s failed on attempt %s: %s", self.name, attempt, exc)
        failure = {
            "tool": self.name,
            "status": "failed",
            "error": str(last_error),
        }
        self._audit(payload, failure, "failed")
        if isinstance(last_error, Exception):
            raise last_error
        raise ToolFailure(f"{self.name} failed without an exception object")

    def _audit(self, payload: dict[str, Any], result: dict[str, Any], status: str) -> None:
        log_path = self.audit_dir / f"{self.name}.log"
        entry = {
            "timestamp": utc_now(),
            "tool": self.name,
            "status": status,
            "payload": payload,
            "result": result,
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

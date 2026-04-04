from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import BootstrapReport, to_dict, utc_now


class ReportWriter:
    def __init__(self, report_dir: Path) -> None:
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def write_bootstrap(self, status: str, summary: str, details: dict[str, Any]) -> Path:
        report = BootstrapReport(status=status, summary=summary, details=details)
        path = self.report_dir / f"bootstrap-{report.generated_at.replace(':', '-')}.json"
        path.write_text(json.dumps(to_dict(report), indent=2))
        return path

    def write_session_report(
        self,
        session_dir: Path,
        report_type: str,
        status: str,
        summary: str,
        details: dict[str, Any],
    ) -> Path:
        session_reports = session_dir / "reports"
        session_reports.mkdir(parents=True, exist_ok=True)
        data = {
            "report_type": report_type,
            "generated_at": utc_now(),
            "status": status,
            "summary": summary,
            "details": details,
        }
        path = session_reports / f"{report_type}.json"
        path.write_text(json.dumps(data, indent=2))
        return path

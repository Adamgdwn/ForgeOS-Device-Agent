from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.reporting import ReportWriter
from app.core.policy import PolicyEngine
from app.core.session_manager import SessionManager
from app.core.state_machine import is_transition_allowed
from app.tools.device_probe import DeviceProbeTool
from app.tools.feasibility_assessor import FeasibilityAssessorTool
from app.tools.strategy_selector import BuildStrategySelectorTool
from app.tools.vscode_opener import VSCodeOpenerTool


class ForgeOrchestrator:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sessions = SessionManager(root)
        self.reports = ReportWriter(root / "output")
        self.policy = PolicyEngine(root / "master" / "policies" / "default_policy.json").load()
        self.device_probe = DeviceProbeTool(root)
        self.assessor = FeasibilityAssessorTool(root)
        self.strategy_selector = BuildStrategySelectorTool(root)
        self.vscode_opener = VSCodeOpenerTool(root)

    def handle_device_event(self, event: dict[str, Any]) -> Path:
        probe_result = self.device_probe.execute({"event": event})
        session_dir = self.sessions.create_or_resume(probe_result["device"])
        if self.policy.open_vscode_on_session_create:
            self.vscode_opener.execute({"target_path": str(session_dir), "new_window": True})
        assessment = self.assessor.execute({"device": probe_result["device"], "session_dir": str(session_dir)})
        self.sessions.annotate(session_dir, assessment["summary"])
        state = self.sessions.load_session_state(session_dir)

        if assessment["support_status"] == "blocked":
            if is_transition_allowed(state.state, state.state.__class__.BLOCKED):
                self.sessions.transition(session_dir, state.state.__class__.BLOCKED, assessment["summary"])
        else:
            strategy = self.strategy_selector.execute(
                {"assessment": assessment, "device": probe_result["device"]}
            )
            updated = self.sessions.load_session_state(session_dir)
            updated.selected_strategy = strategy["strategy_id"]
            updated.support_status = updated.support_status.__class__(assessment["support_status"])
            self.sessions.write_session_state(session_dir, updated)
            if is_transition_allowed(updated.state, updated.state.__class__.PATH_SELECT):
                self.sessions.transition(
                    session_dir,
                    updated.state.__class__.PATH_SELECT,
                    f"Selected strategy {strategy['strategy_id']}",
                )

        self.reports.write_session_report(
            session_dir,
            report_type="assessment",
            status=assessment["support_status"],
            summary=assessment["summary"],
            details={
                "event": event,
                "assessment": assessment,
            },
        )
        self.logger.info("Handled device event for session %s", session_dir.name)
        return session_dir

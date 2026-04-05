from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.knowledge import KnowledgeEngine
from app.core.codex_handoff import CodexHandoffEngine
from app.core.connection_engine import ConnectionEngine
from app.core.connection_playbook import ConnectionPlaybookEngine
from app.core.orchestrator import ForgeOrchestrator
from app.core.policy import PolicyEngine
from app.core.models import (
    GoogleServicesPreference,
    PriorityFocus,
    TechnicalComfort,
    UserPersona,
    utc_now,
)
from app.core.session_manager import SessionManager
from app.integrations import adb, fastboot, fastbootd
from app.integrations.udev import list_usb_mobile_devices
from app.tools.strategy_selector import BuildStrategySelectorTool


class ForgeControlApp:
    def __init__(self, root: Path, bootstrap_report: dict[str, object]) -> None:
        self.project_root = root
        self.bootstrap_report = bootstrap_report
        self.devices_dir = root / "devices"
        self.knowledge = KnowledgeEngine(root)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.codex_handoff = CodexHandoffEngine(root)
        self.connection_engine = ConnectionEngine(root)
        self.connection_playbooks = ConnectionPlaybookEngine(root)
        self.orchestrator = ForgeOrchestrator(root)
        self.policy = PolicyEngine(root / "master" / "policies" / "default_policy.json").load()
        self.sessions = SessionManager(root)
        self.strategy_selector = BuildStrategySelectorTool(root)
        self.current_session_dir: Path | None = None
        self.layout_mode = "wide"
        self.last_refresh_reason = "Startup"

        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setApplicationName("ForgeOS Device Agent")
        self.qt_app.setStyleSheet(self._stylesheet())

        self.window = QMainWindow()
        self.window.setWindowTitle("ForgeOS Device Agent")
        self.window.resize(1180, 760)
        self.window.setMinimumSize(860, 620)
        self.window.resizeEvent = self._handle_resize

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.window.setCentralWidget(self.scroll)

        central = QWidget()
        self.scroll.setWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        outer.addWidget(self._build_header())

        self.content_grid = QGridLayout()
        self.content_grid.setHorizontalSpacing(14)
        self.content_grid.setVerticalSpacing(14)
        outer.addLayout(self.content_grid)

        self.now_card = self._build_now_what_card()
        self.steps_card = self._build_steps_card()
        self.host_card = self._build_host_card()
        self.profile_card = self._build_profile_card()
        self.connection_help_card = self._build_connection_help_card()
        self.approval_card = self._build_approval_card()
        self.autonomous_card = self._build_autonomous_card()
        self.device_card = self._build_device_card()
        self.help_card = self._build_help_card()
        self._apply_layout_mode("wide")

        self.timer = QTimer()
        self.timer.timeout.connect(self._auto_refresh)
        self.timer.start(3000)
        self.refresh_ui("Startup")

    def _stylesheet(self) -> str:
        return """
        QWidget {
            background: #0c1524;
            color: #e8effb;
            font-family: "DejaVu Sans";
            font-size: 13px;
        }
        QGroupBox {
            background: #13233a;
            border: 1px solid #203957;
            border-radius: 14px;
            margin-top: 10px;
            font-weight: bold;
            padding-top: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 6px 0 6px;
            color: #f3f7ff;
        }
        QLabel[role="title"] {
            color: #eef4ff;
            font-size: 26px;
            font-weight: 700;
        }
        QLabel[role="subtitle"] {
            color: #a9bdd8;
            font-size: 13px;
        }
        QLabel[role="body"] {
            color: #d4e0f0;
        }
        QLabel[role="hint"] {
            color: #b8cae4;
        }
        QTextEdit {
            background: #102137;
            border: 1px solid #29456a;
            border-radius: 10px;
            padding: 8px;
            color: #e4edf8;
            font-family: "DejaVu Sans Mono";
            font-size: 12px;
        }
        QPushButton {
            background: #f7941d;
            color: #102137;
            border: none;
            border-radius: 10px;
            padding: 10px 14px;
            font-weight: 700;
        }
        QPushButton:hover {
            background: #ffb14d;
        }
        QFrame[role="stepblock"] {
            background: #172d49;
            border: 1px solid #284769;
            border-radius: 10px;
        }
        """

    def _build_header(self) -> QWidget:
        box = QFrame()
        self.header_layout = QHBoxLayout(box)
        layout = self.header_layout
        layout.setContentsMargins(0, 0, 0, 0)

        self.header_text_col = QVBoxLayout()
        text_col = self.header_text_col
        title = QLabel("ForgeOS Device Agent")
        title.setProperty("role", "title")
        subtitle = QLabel(
            "Step-by-step Android device assessment for cautious, guided operation"
        )
        subtitle.setProperty("role", "subtitle")
        self.status_label = QLabel("Refresh status: starting up")
        self.status_label.setProperty("role", "subtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        text_col.addWidget(self.status_label)
        layout.addLayout(text_col, 1)

        self.button_col = QHBoxLayout()
        button_col = self.button_col
        for label, callback in [
            ("Refresh", self.manual_refresh),
            ("Open User Guide", lambda: self._open_path(self.project_root / "USER_GUIDE.md")),
            ("Open Devices Folder", lambda: self._open_path(self.devices_dir)),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            button_col.addWidget(button)
        layout.addLayout(button_col)
        return box

    def _build_now_what_card(self) -> QGroupBox:
        group = QGroupBox("Current Objective")
        layout = QVBoxLayout(group)
        self.primary_label = QLabel()
        self.primary_label.setWordWrap(True)
        self.primary_label.setProperty("role", "body")
        self.secondary_label = QLabel()
        self.secondary_label.setWordWrap(True)
        self.secondary_label.setProperty("role", "body")
        self.objective_text = QTextEdit()
        self.objective_text.setReadOnly(True)
        self.objective_text.setMaximumHeight(180)
        layout.addWidget(self.primary_label)
        layout.addWidget(self.secondary_label)
        layout.addWidget(self.objective_text)
        return group

    def _build_host_card(self) -> QGroupBox:
        group = QGroupBox("Host Readiness")
        layout = QVBoxLayout(group)
        self.host_label = QLabel()
        self.host_label.setWordWrap(True)
        self.host_label.setTextFormat(Qt.TextFormat.PlainText)
        self.host_label.setProperty("role", "body")
        self.readiness_label = QLabel()
        self.readiness_label.setWordWrap(True)
        self.readiness_label.setProperty("role", "body")
        layout.addWidget(self.host_label)
        layout.addWidget(self.readiness_label)
        return group

    def _build_device_card(self) -> QGroupBox:
        group = QGroupBox("Current Device Session")
        layout = QVBoxLayout(group)
        self.device_title = QLabel()
        self.device_title.setWordWrap(True)
        self.device_title.setProperty("role", "body")
        self.device_text = QTextEdit()
        self.device_text.setReadOnly(True)
        layout.addWidget(self.device_title)
        layout.addWidget(self.device_text, 1)

        actions = QHBoxLayout()
        self.open_folder_button = QPushButton("Open Session Folder")
        self.open_folder_button.clicked.connect(self._open_current_session)
        self.open_code_button = QPushButton("Open Session In VS Code")
        self.open_code_button.clicked.connect(lambda: self._open_current_session(code=True))
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.open_code_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return group

    def _build_autonomous_card(self) -> QGroupBox:
        group = QGroupBox("Execution Queue")
        layout = QVBoxLayout(group)
        self.autonomous_title = QLabel()
        self.autonomous_title.setWordWrap(True)
        self.autonomous_title.setProperty("role", "body")
        self.autonomous_text = QTextEdit()
        self.autonomous_text.setReadOnly(True)
        layout.addWidget(self.autonomous_title)
        layout.addWidget(self.autonomous_text, 1)
        return group

    def _build_profile_card(self) -> QGroupBox:
        group = QGroupBox("User Profile And OS Goals")
        layout = QVBoxLayout(group)

        self.profile_status = QLabel("Select the intended user and goals for this device session.")
        self.profile_status.setWordWrap(True)
        self.profile_status.setProperty("role", "body")
        layout.addWidget(self.profile_status)

        self.persona_combo = QComboBox()
        self.persona_combo.addItem("Daily user", UserPersona.DAILY.value)
        self.persona_combo.addItem("Senior", UserPersona.SENIOR.value)
        self.persona_combo.addItem("Developer", UserPersona.DEVELOPER.value)
        self.persona_combo.addItem("Child", UserPersona.CHILD.value)
        self.persona_combo.addItem("Privacy focused", UserPersona.PRIVACY.value)

        self.comfort_combo = QComboBox()
        self.comfort_combo.addItem("Low technical comfort", TechnicalComfort.LOW.value)
        self.comfort_combo.addItem("Medium technical comfort", TechnicalComfort.MEDIUM.value)
        self.comfort_combo.addItem("High technical comfort", TechnicalComfort.HIGH.value)

        self.priority_combo = QComboBox()
        for label, value in [
            ("Security", PriorityFocus.SECURITY.value),
            ("Simplicity", PriorityFocus.SIMPLICITY.value),
            ("Performance", PriorityFocus.PERFORMANCE.value),
            ("Battery", PriorityFocus.BATTERY.value),
            ("Privacy", PriorityFocus.PRIVACY.value),
            ("Compatibility", PriorityFocus.COMPATIBILITY.value),
        ]:
            self.priority_combo.addItem(label, value)

        self.google_combo = QComboBox()
        self.google_combo.addItem("Keep Google services", GoogleServicesPreference.KEEP.value)
        self.google_combo.addItem("Reduce Google services", GoogleServicesPreference.REDUCE.value)
        self.google_combo.addItem("Remove Google services where feasible", GoogleServicesPreference.REMOVE.value)

        self.secondary_goal_combo = QComboBox()
        for label, value in [
            ("Simplicity", PriorityFocus.SIMPLICITY.value),
            ("Security", PriorityFocus.SECURITY.value),
            ("Battery", PriorityFocus.BATTERY.value),
            ("Privacy", PriorityFocus.PRIVACY.value),
            ("Compatibility", PriorityFocus.COMPATIBILITY.value),
            ("Performance", PriorityFocus.PERFORMANCE.value),
        ]:
            self.secondary_goal_combo.addItem(label, value)

        self.updates_check = QCheckBox("Reliable updates are required")
        self.updates_check.setChecked(True)
        self.battery_check = QCheckBox("Long battery life is preferred")
        self.battery_check.setChecked(True)
        self.lockdown_check = QCheckBox("Lockdown defaults are preferred")
        self.lockdown_check.setChecked(True)

        for label_text, widget in [
            ("Primary user persona", self.persona_combo),
            ("Technical comfort", self.comfort_combo),
            ("Top priority", self.priority_combo),
            ("Google services preference", self.google_combo),
            ("Secondary goal", self.secondary_goal_combo),
        ]:
            label = QLabel(label_text)
            label.setProperty("role", "hint")
            layout.addWidget(label)
            layout.addWidget(widget)

        layout.addWidget(self.updates_check)
        layout.addWidget(self.battery_check)
        layout.addWidget(self.lockdown_check)

        save_button = QPushButton("Save Profile And Recompute Strategy")
        save_button.clicked.connect(self.save_profile_and_recompute)
        layout.addWidget(save_button)
        return group

    def _build_connection_help_card(self) -> QGroupBox:
        group = QGroupBox("Connection Setup For This Phone")
        layout = QVBoxLayout(group)
        self.connection_help_title = QLabel("ForgeOS will show model-aware phone-side setup steps here.")
        self.connection_help_title.setWordWrap(True)
        self.connection_help_title.setProperty("role", "body")
        self.connection_help_text = QTextEdit()
        self.connection_help_text.setReadOnly(True)
        layout.addWidget(self.connection_help_title)
        layout.addWidget(self.connection_help_text, 1)
        return group

    def _build_steps_card(self) -> QGroupBox:
        group = QGroupBox("Agent Execution")
        layout = QVBoxLayout(group)
        self.steps_title = QLabel("ForgeOS will show the live execution checklist here.")
        self.steps_title.setWordWrap(True)
        self.steps_title.setProperty("role", "body")
        self.steps_text = QTextEdit()
        self.steps_text.setReadOnly(True)
        layout.addWidget(self.steps_title)
        layout.addWidget(self.steps_text, 1)
        return group

    def _build_approval_card(self) -> QGroupBox:
        group = QGroupBox("Wipe Approval And Execution")
        layout = QVBoxLayout(group)

        self.approval_status = QLabel(
            "Destructive execution is blocked until you explicitly approve wipe and rebuild for the current session."
        )
        self.approval_status.setWordWrap(True)
        self.approval_status.setProperty("role", "body")
        layout.addWidget(self.approval_status)

        self.restore_confirm_check = QCheckBox("I confirm the restore path has been reviewed")
        layout.addWidget(self.restore_confirm_check)

        phrase_label = QLabel("Type WIPE_AND_REBUILD to allow destructive execution")
        phrase_label.setProperty("role", "hint")
        layout.addWidget(phrase_label)
        self.confirmation_input = QLineEdit()
        self.confirmation_input.setPlaceholderText("WIPE_AND_REBUILD")
        layout.addWidget(self.confirmation_input)

        notes_label = QLabel("Optional operator notes")
        notes_label.setProperty("role", "hint")
        layout.addWidget(notes_label)
        self.approval_notes = QTextEdit()
        self.approval_notes.setMaximumHeight(80)
        layout.addWidget(self.approval_notes)

        buttons = QHBoxLayout()
        approve_button = QPushButton("Record Wipe Approval")
        approve_button.clicked.connect(self.record_wipe_approval)
        dry_run_button = QPushButton("Run Approved Dry Run")
        dry_run_button.clicked.connect(lambda: self.execute_flash(live_mode=False))
        live_button = QPushButton("Run Live Wipe And Flash")
        live_button.clicked.connect(lambda: self.execute_flash(live_mode=True))
        buttons.addWidget(approve_button)
        buttons.addWidget(dry_run_button)
        buttons.addWidget(live_button)
        layout.addLayout(buttons)

        self.flash_plan_text = QTextEdit()
        self.flash_plan_text.setReadOnly(True)
        layout.addWidget(self.flash_plan_text, 1)
        return group

    def _build_help_card(self) -> QGroupBox:
        group = QGroupBox("Artifacts")
        layout = QVBoxLayout(group)
        for label, path in [
            ("Open User Guide", self.project_root / "USER_GUIDE.md"),
            ("Open Session Folder", self.project_root / "devices"),
            ("Open Session Backup", self.project_root / "devices"),
            ("Open Logs", self.project_root / "logs"),
            ("Open Output Reports", self.project_root / "output"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, p=path: self._open_path(p))
            layout.addWidget(button)
        layout.addStretch(1)
        return group

    def _set_text_preserve_scroll(self, widget: QTextEdit, text: str) -> None:
        scrollbar = widget.verticalScrollBar()
        previous_value = scrollbar.value()
        was_at_bottom = previous_value >= max(0, scrollbar.maximum() - 2)
        widget.setPlainText(text)
        new_max = scrollbar.maximum()
        if was_at_bottom:
            scrollbar.setValue(new_max)
        else:
            scrollbar.setValue(min(previous_value, new_max))

    def _collect_sessions(self) -> list[Path]:
        if not self.devices_dir.exists():
            return []
        return sorted(
            [
                path
                for path in self.devices_dir.iterdir()
                if path.is_dir() and (path / "session-state.json").exists()
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def _active_serials(self) -> set[str]:
        serials: set[str] = set()
        for loader in (adb.list_devices, fastboot.list_devices, fastbootd.list_devices):
            try:
                for device in loader():
                    serial = device.get("serial")
                    if serial:
                        serials.add(serial)
            except Exception:  # noqa: BLE001
                continue
        return serials

    def _current_live_session(self, sessions: list[Path]) -> Path | None:
        active_serials = self._active_serials()
        if not active_serials:
            return None
        for session_dir in sessions:
            profile_path = session_dir / "device-profile.json"
            if not profile_path.exists():
                continue
            profile = json.loads(profile_path.read_text())
            if profile.get("serial") in active_serials:
                return session_dir
        return None

    def _usb_only_device_summary(self) -> dict[str, str] | None:
        active_serials = self._active_serials()
        if active_serials:
            return None
        devices = list_usb_mobile_devices()
        if not devices:
            return None
        return devices[0]

    def _compose_host_status(self) -> tuple[str, str]:
        details = self.bootstrap_report
        lines = [
            f"VS Code CLI: {'ready' if details.get('code_available') else 'missing'}",
            f"ADB: {'ready' if details.get('adb_available') else 'missing'}",
            f"Fastboot: {'ready' if details.get('fastboot_available') else 'missing'}",
            f"udev support: {'present' if details.get('udev_present') else 'missing'}",
            f"Workspace file: {details.get('workspace_file')}",
        ]
        if details.get("adb_available") and details.get("fastboot_available"):
            summary = "This computer is ready for guided device assessment."
        else:
            summary = (
                "ForgeOS can start, but missing transport tools will limit automatic phone detection. "
                "Use the bundled local tools path or rerun the environment setup if needed."
            )
        return "\n".join(lines), summary

    def _format_device_text(self, session_dir: Path) -> str:
        profile_path = session_dir / "device-profile.json"
        state_path = session_dir / "session-state.json"
        report_path = session_dir / "reports" / "assessment.json"
        engagement_path = session_dir / "reports" / "engagement.json"

        profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        engagement = json.loads(engagement_path.read_text()) if engagement_path.exists() else {}
        family_summary = self.knowledge.lookup_family_summary(
            profile.get("manufacturer"),
            profile.get("model"),
        )

        lines = [
            f"Session folder: {session_dir}",
            f"Current state: {state.get('state', 'unknown')}",
            f"Support status: {state.get('support_status', 'unknown')}",
            f"Selected strategy: {state.get('selected_strategy') or 'not selected yet'}",
            "",
            f"Manufacturer: {profile.get('manufacturer') or 'unknown'}",
            f"Model: {profile.get('model') or 'unknown'}",
            f"Serial: {profile.get('serial') or 'unknown'}",
            f"Transport: {profile.get('transport') or 'unknown'}",
            f"Android version: {profile.get('android_version') or 'unknown'}",
            f"Bootloader locked: {profile.get('bootloader_locked')}",
            f"Verified boot state: {profile.get('verified_boot_state') or 'unknown'}",
        ]

        if family_summary:
            lines.extend(
                [
                    "",
                    "Controlled learning summary:",
                    f"Device family key: {family_summary.get('family_key')}",
                    f"Observed sessions: {family_summary.get('observations')}",
                    f"Confidence: {family_summary.get('confidence')}",
                    f"Support level: {family_summary.get('support_level')}",
                    f"Recommended strategy: {family_summary.get('recommended_strategy')}",
                ]
            )

        summary = report.get("summary")
        if summary:
            lines.extend(["", "Assessment summary:", summary])

        engagement_summary = engagement.get("summary")
        if engagement_summary:
            lines.extend(
                [
                    "",
                    "Autonomous engagement:",
                    f"Status: {engagement.get('status')}",
                    engagement_summary,
                ]
            )
            next_steps = engagement.get("details", {}).get("next_steps") or []
            if next_steps:
                lines.append("Next steps:")
                lines.extend(f"- {step}" for step in next_steps)

        notes = state.get("notes") or []
        if notes:
            lines.extend(["", "Recent notes:"])
            lines.extend(f"- {note}" for note in notes[-4:])
        return "\n".join(lines)

    def _format_autonomous_text(self, session_dir: Path) -> tuple[str, str]:
        engagement_path = session_dir / "reports" / "engagement.json"
        blocker_path = session_dir / "reports" / "blocker.json"
        build_plan_path = session_dir / "reports" / "build_plan.json"
        execution_queue_path = session_dir / "reports" / "execution_queue.json"
        if not engagement_path.exists():
            return (
                "No autonomous engagement report yet.",
                "ForgeOS has not recorded any autonomous engagement attempts for this session yet.",
            )

        engagement = json.loads(engagement_path.read_text())
        blocker = json.loads(blocker_path.read_text()) if blocker_path.exists() else {}
        build_plan = json.loads(build_plan_path.read_text()) if build_plan_path.exists() else {}
        execution_queue = json.loads(execution_queue_path.read_text()) if execution_queue_path.exists() else {}
        details = engagement.get("details", {})
        actions_attempted = details.get("actions_attempted") or []
        findings = details.get("findings") or []
        next_steps = details.get("next_steps") or []

        title = (
            f"Current autonomous status: {engagement.get('status', 'unknown')}"
        )

        lines = [
            f"Summary: {engagement.get('summary', 'No summary available')}",
        ]

        if blocker:
            lines.extend(
                [
                    "",
                    "Current blocker:",
                    f"- type: {blocker.get('status', blocker.get('details', {}).get('blocker_type', 'unknown'))}",
                    f"- summary: {blocker.get('summary', 'No blocker summary available')}",
                ]
            )

        if build_plan:
            lines.extend(
                [
                    "",
                    "Resolved build path:",
                    f"- os path: {build_plan.get('details', {}).get('os_path', 'unknown')}",
                    f"- why: {build_plan.get('summary', 'No build-path summary available')}",
                ]
            )

        if actions_attempted:
            lines.extend(["", "Actions attempted:"])
            for action in actions_attempted:
                name = action.get("action", "unknown")
                ok = action.get("ok")
                outcome = "ok" if ok else "not ok"
                extra = action.get("reason") or action.get("stderr") or action.get("stdout") or ""
                lines.append(f"- {name}: {outcome}")
                if extra:
                    lines.append(f"  {extra}")

        if findings:
            lines.extend(["", "Findings:"])
            lines.extend(f"- {finding}" for finding in findings)

        if next_steps:
            lines.extend(["", "Agent is waiting for:"])
            lines.extend(f"- {step}" for step in next_steps)
        else:
            lines.extend(["", "Agent is waiting for:", "- No user-side action listed right now."])

        if execution_queue:
            retry_details = execution_queue.get("details", {}).get("retry_plan", {})
            lines.extend(
                [
                    "",
                    "Execution queue:",
                    f"- action: {retry_details.get('action', execution_queue.get('status', 'unknown'))}",
                    f"- rationale: {retry_details.get('rationale', execution_queue.get('summary', 'No queue rationale available'))}",
                ]
            )

        return title, "\n".join(lines)

    def _current_codex_files(self, session_dir: Path) -> list[str]:
        codex_dir = session_dir / "codex"
        files = []
        for filename in ["CODEX_TASK.md", "codex-handoff.json", "device-session.code-workspace"]:
            path = codex_dir / filename
            if path.exists():
                files.append(str(path))
        return files

    def _set_combo_by_value(self, combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _load_profile_form(self, session_dir: Path) -> None:
        profile = self.sessions.load_user_profile(session_dir)
        goals = self.sessions.load_os_goals(session_dir)
        self._set_combo_by_value(self.persona_combo, profile.persona.value)
        self._set_combo_by_value(self.comfort_combo, profile.technical_comfort.value)
        self._set_combo_by_value(self.priority_combo, profile.primary_priority.value)
        self._set_combo_by_value(self.google_combo, profile.google_services_preference.value)
        self._set_combo_by_value(self.secondary_goal_combo, goals.secondary_goal.value)
        self.updates_check.setChecked(goals.requires_reliable_updates)
        self.battery_check.setChecked(goals.prefers_long_battery_life)
        self.lockdown_check.setChecked(goals.prefers_lockdown_defaults)

    def save_profile_and_recompute(self) -> None:
        if not self.current_session_dir:
            self.profile_status.setText("No current device session is available yet.")
            return

        user_profile = self.sessions.load_user_profile(self.current_session_dir)
        user_profile.persona = UserPersona(self.persona_combo.currentData())
        user_profile.technical_comfort = TechnicalComfort(self.comfort_combo.currentData())
        user_profile.primary_priority = PriorityFocus(self.priority_combo.currentData())
        user_profile.google_services_preference = GoogleServicesPreference(
            self.google_combo.currentData()
        )
        self.sessions.write_user_profile(self.current_session_dir, user_profile)

        os_goals = self.sessions.load_os_goals(self.current_session_dir)
        os_goals.top_goal = PriorityFocus(self.priority_combo.currentData())
        os_goals.secondary_goal = PriorityFocus(self.secondary_goal_combo.currentData())
        os_goals.requires_reliable_updates = self.updates_check.isChecked()
        os_goals.prefers_long_battery_life = self.battery_check.isChecked()
        os_goals.prefers_lockdown_defaults = self.lockdown_check.isChecked()
        self.sessions.write_os_goals(self.current_session_dir, os_goals)

        assessment_path = self.current_session_dir / "reports" / "assessment.json"
        assessment_report = json.loads(assessment_path.read_text()) if assessment_path.exists() else {
            "details": {"assessment": {"support_status": "research_only", "summary": "No assessment report yet."}}
        }
        assessment = assessment_report.get("details", {}).get("assessment", {})
        strategy = self.strategy_selector.execute(
            {
                "assessment": assessment,
                "device": json.loads((self.current_session_dir / "device-profile.json").read_text()),
                "user_profile": {
                    "persona": user_profile.persona.value,
                    "technical_comfort": user_profile.technical_comfort.value,
                    "primary_priority": user_profile.primary_priority.value,
                    "google_services_preference": user_profile.google_services_preference.value,
                },
                "os_goals": {
                    "top_goal": os_goals.top_goal.value,
                    "secondary_goal": os_goals.secondary_goal.value,
                    "requires_reliable_updates": os_goals.requires_reliable_updates,
                    "prefers_long_battery_life": os_goals.prefers_long_battery_life,
                    "prefers_lockdown_defaults": os_goals.prefers_lockdown_defaults,
                },
            }
        )
        state = self.sessions.load_session_state(self.current_session_dir)
        state.selected_strategy = strategy["strategy_id"]
        self.sessions.write_session_state(self.current_session_dir, state)
        profile_data = self.sessions.load_device_profile(self.current_session_dir)
        assessment = assessment_report.get("details", {}).get("assessment", {})
        engagement_path = self.current_session_dir / "reports" / "engagement.json"
        engagement_report = json.loads(engagement_path.read_text()) if engagement_path.exists() else {
            "details": {"engagement_status": "unknown", "summary": "No engagement report yet."}
        }
        engagement = {
            "engagement_status": engagement_report.get("status", "unknown"),
            "summary": engagement_report.get("summary", "No engagement summary available."),
            **engagement_report.get("details", {}),
        }
        plan = self.connection_engine.build_plan(
            profile_data,
            state,
            assessment,
            engagement,
        )
        self.connection_engine.write_plan(self.current_session_dir, plan)
        self.codex_handoff.prepare(
            self.current_session_dir,
            profile_data,
            state,
            user_profile,
            os_goals,
            assessment,
            engagement,
            plan,
        )
        self.profile_status.setText(
            f"Saved profile. Recommended OS path is now `{strategy['strategy_id']}`."
        )
        self.refresh_ui("Profile updated")

    def record_wipe_approval(self) -> None:
        if not self.current_session_dir:
            self.approval_status.setText("No current session is loaded yet, so approval cannot be recorded.")
            return
        confirmation_phrase = self.confirmation_input.text().strip()
        restore_confirmed = self.restore_confirm_check.isChecked()
        notes = self.approval_notes.toPlainText().strip()
        self.orchestrator.record_wipe_approval(
            self.current_session_dir,
            approved=True,
            confirmation_phrase=confirmation_phrase,
            restore_path_confirmed=restore_confirmed,
            notes=notes,
        )
        self.approval_status.setText(
            "Approval record saved for this session. You can now run a dry run, and live destructive execution remains policy-gated."
        )
        self.refresh_ui("Approval recorded")

    def execute_flash(self, live_mode: bool) -> None:
        if not self.current_session_dir:
            self.approval_status.setText("No current session is loaded yet, so there is nothing to execute.")
            return
        if live_mode and not self.policy.allow_live_destructive_actions:
            self.approval_status.setText(
                "Policy currently blocks live destructive actions. Enable it in master/policies/default_policy.json only when you are ready."
            )
            return
        result = self.orchestrator.execute_approved_flash(self.current_session_dir, live_mode=live_mode)
        self.approval_status.setText(result["summary"])
        if live_mode:
            QMessageBox.information(
                self.window,
                "Live Execution",
                result["summary"],
            )
        self.refresh_ui("Execution started" if live_mode else "Dry run executed")

    def refresh_ui(self, reason: str = "Auto refresh") -> None:
        sessions = self._collect_sessions()
        live_session = self._current_live_session(sessions)
        usb_only_device = self._usb_only_device_summary()
        host_text, readiness = self._compose_host_status()
        self.host_label.setText(host_text)
        self.readiness_label.setText(readiness)
        self.last_refresh_reason = reason

        latest_saved = sessions[0] if sessions else None

        if not latest_saved:
            self.current_session_dir = None
            if usb_only_device:
                playbook = self._playbook_for_context(
                    usb_only_device.get("vendor_hint"),
                    None,
                    "usb_only_detected",
                    usb_only_device.get("transport_hint", "usb-mtp"),
                )
                self._set_objective_panel(
                    f"{usb_only_device.get('vendor_hint')} phone detected, but it is still in USB-only mode.",
                    "ForgeOS is already retrying safe engagement. The only remaining work is on the phone itself.",
                    playbook=playbook,
                    agent_action="Watching for adb or fastboot, retrying adb startup, and waiting for the phone to expose a manageable transport.",
                )
                title, checklist, agent_status = self._build_execution_checklist(
                    profile={
                        "manufacturer": usb_only_device.get("vendor_hint"),
                        "model": "phone",
                    },
                    state={"state": "QUESTION_GATE", "support_status": "research_only"},
                    engagement={"status": "usb_only_detected"},
                    playbook=playbook,
                    flash_plan=None,
                    backup_plan=None,
                    approval=None,
                    live_session=False,
                )
                self._set_execution_checklist(title, checklist, agent_status)
            else:
                self._set_objective_panel(
                    "ForgeOS is ready for one phone.",
                    "Keep this window open and connect a test device. The agent will create the session automatically.",
                    agent_action="Keeping the environment ready, watching USB, adb, and fastboot, and preparing the session workspace.",
                )
                title, checklist, agent_status = self._build_execution_checklist(
                    profile=None,
                    state=None,
                    engagement=None,
                    playbook=None,
                    flash_plan=None,
                    backup_plan=None,
                    approval=None,
                    live_session=False,
                )
                self._set_execution_checklist(title, checklist, agent_status)
            self.device_title.setText("No device session detected yet.")
            waiting_text = (
                "Waiting for a manageable device.\n\n"
                "Recommended first test:\n"
                "- Start with a non-primary phone.\n"
                "- Use a reliable USB data cable.\n"
                "- Enable USB debugging if Android is booted.\n"
                "- Wait for a session folder to appear under devices/.\n"
            )
            if usb_only_device:
                waiting_text += (
                    "\nUSB observation:\n"
                    f"- {usb_only_device.get('description')}\n"
                    "- Current mode looks like MTP or generic USB only.\n"
                    "- ForgeOS needs adb, fastboot, or recovery visibility to create a device session.\n"
                )
            self._set_text_preserve_scroll(self.device_text, waiting_text)
            self.autonomous_title.setText("Current autonomous status: waiting for a manageable device")
            self.profile_status.setText("Connect or select a device session before setting the user profile.")
            self.connection_help_title.setText("No device session is loaded yet.")
            self._set_text_preserve_scroll(
                self.connection_help_text,
                "Connect a phone and ForgeOS will show vendor- and model-specific setup steps here.\n\n"
                "This panel is meant to tell the operator exactly how to get from USB-only visibility to adb, fastboot, or another manageable transport."
            )
            self.approval_status.setText("Connect or select a device session before recording wipe approval.")
            self._set_text_preserve_scroll(self.flash_plan_text, "No flash plan is available yet.")
            if usb_only_device:
                self._set_text_preserve_scroll(
                    self.autonomous_text,
                    "ForgeOS can see a phone at the USB level and is waiting for a manageable transport.\n\n"
                    "Agent is waiting for:\n"
                    "- Unlock the phone.\n"
                    "- Enable USB debugging.\n"
                    "- Approve the computer trust prompt.\n"
                    "- Reconnect the USB cable if needed.\n"
                )
            else:
                self._set_text_preserve_scroll(
                    self.autonomous_text,
                    "ForgeOS is idle and waiting for a phone that exposes USB, adb, fastboot, or recovery visibility."
                )
            self.open_folder_button.setEnabled(False)
            self.open_code_button.setEnabled(False)
            self._update_card_visibility(False, bool(usb_only_device), "usb_only_detected" if usb_only_device else "unknown")
            self._update_refresh_status(reason, has_live_device=False, has_usb_only=bool(usb_only_device))
            return

        self.current_session_dir = live_session or latest_saved
        state = json.loads((self.current_session_dir / "session-state.json").read_text())
        profile = json.loads((self.current_session_dir / "device-profile.json").read_text())
        engagement_path = self.current_session_dir / "reports" / "engagement.json"
        engagement_report = json.loads(engagement_path.read_text()) if engagement_path.exists() else {}
        engagement_status = engagement_report.get("status", engagement_report.get("engagement_status", "unknown"))
        playbook = self._playbook_for_context(
            profile.get("manufacturer"),
            profile.get("model"),
            engagement_status,
            profile.get("transport", "unknown"),
        )

        if live_session:
            self._set_objective_panel(
                f"{profile.get('manufacturer') or 'Unknown'} {profile.get('model') or 'device'} is connected now.",
                "ForgeOS is handling assessment, planning, backup capture, and transport monitoring automatically.",
                playbook=playbook,
                agent_action="Continuing device assessment, maintaining the session, capturing backup evidence, and preparing the next safe step.",
            )
        elif usb_only_device:
            self._set_objective_panel(
                f"{usb_only_device.get('vendor_hint')} phone connected, but still not in adb or fastboot.",
                "ForgeOS is showing the latest saved session for reference while it keeps retrying safe host-side engagement.",
                playbook=playbook,
                agent_action="Retrying adb engagement, watching for transport changes, and keeping the device session ready to resume automatically.",
            )
        else:
            latest_profile = json.loads((latest_saved / "device-profile.json").read_text())
            self._set_objective_panel(
                "No phone is currently connected.",
                f"ForgeOS is showing the latest saved session for {latest_profile.get('manufacturer') or 'Unknown'} "
                f"{latest_profile.get('model') or 'device'} while waiting for a live device.",
                agent_action="Keeping the last session available for reference and waiting for the next real device event.",
            )

        title_prefix = "Live session" if live_session else "Latest saved session"
        self.device_title.setText(
            f"{title_prefix}: {self.current_session_dir.name}  |  State: {state.get('state', 'unknown')}"
        )
        self._set_text_preserve_scroll(self.device_text, self._format_device_text(self.current_session_dir))
        autonomous_title, autonomous_text = self._format_autonomous_text(self.current_session_dir)
        codex_files = self._current_codex_files(self.current_session_dir)
        if codex_files:
            autonomous_text += "\n\nCodex handoff files:\n" + "\n".join(f"- {path}" for path in codex_files)
        self.autonomous_title.setText(autonomous_title)
        self._set_text_preserve_scroll(self.autonomous_text, autonomous_text)
        self._load_profile_form(self.current_session_dir)
        self.profile_status.setText("Profile is loaded for this session. Save changes to recompute the OS path.")
        self._refresh_connection_help(self.current_session_dir)
        flash_plan_path = self.current_session_dir / "backup" / "backup-plan.json"
        backup_plan = json.loads(flash_plan_path.read_text()) if flash_plan_path.exists() else {}
        session_flash_plan = self.sessions.load_flash_plan(self.current_session_dir)
        approval = self.sessions.load_destructive_approval(self.current_session_dir)
        checklist_title, checklist, agent_status = self._build_execution_checklist(
            profile=profile,
            state=state,
            engagement=engagement_report,
            playbook=playbook,
            flash_plan={
                "build_path": session_flash_plan.build_path,
                "restore_path_available": session_flash_plan.restore_path_available,
            }
            if session_flash_plan
            else None,
            backup_plan=backup_plan,
            approval={
                "approved": approval.approved,
                "restore_path_confirmed": approval.restore_path_confirmed,
            },
            live_session=bool(live_session),
        )
        self._set_execution_checklist(checklist_title, checklist, agent_status)
        self._refresh_approval_panel(self.current_session_dir)
        self.open_folder_button.setEnabled(True)
        self.open_code_button.setEnabled(True)
        self._update_card_visibility(True, bool(usb_only_device), engagement_status)
        self._update_refresh_status(reason, has_live_device=bool(live_session), has_usb_only=bool(usb_only_device))

    def _refresh_connection_help(self, session_dir: Path) -> None:
        profile = json.loads((session_dir / "device-profile.json").read_text())
        engagement_path = session_dir / "reports" / "engagement.json"
        engagement = json.loads(engagement_path.read_text()) if engagement_path.exists() else {}
        playbook = self.connection_playbooks.resolve(
            profile.get("manufacturer"),
            profile.get("model"),
            engagement.get("status", engagement.get("engagement_status", "unknown")),
            profile.get("transport", "unknown"),
        )
        self.connection_help_title.setText(playbook["title"])
        lines = [
            playbook["summary"],
            "",
            "How to find USB debugging:",
        ]
        if "samsung" in str(playbook.get("playbook_id", "")):
            lines.extend(
                [
                    "- Open Settings.",
                    "- Open About device or About phone.",
                    "- If Software information exists, open it.",
                    "- Tap Build number 7 times.",
                    "- Go back and open Developer Options.",
                    "- Turn on USB debugging.",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "- Open Settings.",
                    "- Open About phone.",
                    "- Tap Build number 7 times.",
                    "- Go back and open Developer Options.",
                    "- Turn on USB debugging.",
                    "",
                ]
            )
        lines.extend(
            [
            "Steps:",
            ]
        )
        lines.extend(f"- {step}" for step in playbook.get("steps", []))
        lines.extend(
            [
                "",
                f"Expected next state: {playbook.get('expected_next_state', 'unknown')}",
            ]
        )
        troubleshooting = playbook.get("troubleshooting", [])
        if troubleshooting:
            lines.extend(["", "Troubleshooting:"])
            lines.extend(f"- {item}" for item in troubleshooting)
        self._set_text_preserve_scroll(self.connection_help_text, "\n".join(lines))

    def _playbook_for_context(
        self,
        manufacturer: str | None,
        model: str | None,
        engagement_status: str,
        transport: str,
    ) -> dict[str, object]:
        return self.connection_playbooks.resolve(
            manufacturer,
            model,
            engagement_status,
            transport,
        )

    def _set_objective_panel(
        self,
        headline: str,
        subheadline: str,
        playbook: dict[str, object] | None = None,
        agent_action: str | None = None,
    ) -> None:
        self.primary_label.setText(headline)
        self.secondary_label.setText(subheadline)
        if playbook:
            steps = playbook.get("steps", [])[:2]
            lines = [
                "Agent is doing now:",
                f"- {agent_action or 'Watching USB, adb, and fastboot, retrying safe engagement, and updating the session automatically.'}",
                "",
                "You only need to do:",
            ]
            lines.extend(f"- {step}" for step in steps)
            expected = playbook.get("expected_next_state")
            if expected:
                lines.extend(["", f"Expected next result: {expected}"])
            self._set_text_preserve_scroll(self.objective_text, "\n".join(lines))
        else:
            self._set_text_preserve_scroll(
                self.objective_text,
                "\n".join(
                    [
                        "Agent is doing now:",
                        f"- {agent_action or 'Waiting for a phone and keeping the workspace ready.'}",
                        "",
                        "You only need to do:",
                        "- Connect one Android phone with a good USB data cable.",
                        "- Unlock the phone if Android is booted.",
                        "- Approve USB debugging if the phone asks.",
                    ]
                ),
            )

    def _set_execution_checklist(
        self,
        title: str,
        checklist: list[str],
        agent_status: list[str] | None = None,
    ) -> None:
        self.steps_title.setText(title)
        lines: list[str] = []
        if agent_status:
            lines.extend(["Agent status:"])
            lines.extend(f"- {item}" for item in agent_status)
            lines.append("")
        lines.append("Execution checklist:")
        lines.extend(f"- {item}" for item in checklist)
        self._set_text_preserve_scroll(self.steps_text, "\n".join(lines))

    def _build_execution_checklist(
        self,
        profile: dict[str, object] | None,
        state: dict[str, object] | None,
        engagement: dict[str, object] | None,
        playbook: dict[str, object] | None,
        flash_plan: dict[str, object] | None,
        backup_plan: dict[str, object] | None,
        approval: dict[str, object] | None,
        live_session: bool,
    ) -> tuple[str, list[str], list[str]]:
        profile = profile or {}
        state = state or {}
        engagement = engagement or {}
        playbook = playbook or {}
        flash_plan = flash_plan or {}
        backup_plan = backup_plan or {}
        approval = approval or {}
        manufacturer = profile.get("manufacturer") or "Unknown"
        model = profile.get("model") or "device"
        engagement_status = engagement.get("status", engagement.get("engagement_status", "unknown"))
        support_status = state.get("support_status", "unknown")
        state_name = state.get("state", "unknown")

        agent_status = [
            f"Current session state: {state_name}",
            f"Support status: {support_status}",
            f"Transport status: {engagement_status}",
        ]
        if backup_plan:
            agent_status.append("Pre-wipe backup bundle is present.")
        else:
            agent_status.append("Pre-wipe backup bundle has not been captured yet.")

        if engagement_status == "usb_only_detected":
            checklist = list(playbook.get("steps", []))[:4]
            checklist.append("Wait for ForgeOS to detect adb, fastboot, or another manageable transport automatically.")
            return (
                f"Connection checklist for {manufacturer} {model}",
                checklist,
                agent_status + [
                    "ForgeOS is retrying safe adb engagement and watching for a transport change."
                ],
            )

        if engagement_status == "awaiting_user_approval":
            checklist = list(playbook.get("steps", []))[:3]
            checklist.append("Keep the phone unlocked until ForgeOS shows adb connected.")
            return (
                f"Trust approval checklist for {manufacturer} {model}",
                checklist,
                agent_status + [
                    "ForgeOS has already reached adb visibility and is waiting only for the phone-side trust prompt."
                ],
            )

        if live_session and support_status in {"actionable", "research_only"}:
            checklist = [
                "Leave the phone connected while ForgeOS keeps updating the session.",
                "Review the connection, backup, and flash-plan panels.",
            ]
            if not backup_plan:
                checklist.append("Wait for ForgeOS to capture the pre-wipe backup bundle before considering destructive actions.")
            if flash_plan:
                checklist.append("Review the flash plan and restore notes before recording wipe approval.")
            if not approval.get("approved"):
                checklist.append("Only when you are satisfied with the plan, type WIPE_AND_REBUILD and record approval.")
            else:
                checklist.append("Run an approved dry run first. Use live wipe and flash only when policy explicitly allows it.")
            return (
                f"Execution checklist for {manufacturer} {model}",
                checklist,
                agent_status + [
                    "ForgeOS is handling assessment, backup planning, and execution preparation automatically."
                ],
            )

        checklist = [
            "Connect one Android phone with a good USB data cable.",
            "Keep the phone unlocked if Android is booted.",
            "Approve USB debugging if the phone asks.",
            "Let ForgeOS create or resume the device session automatically.",
        ]
        return (
            "Getting started checklist",
            checklist,
            ["ForgeOS is waiting for a live device and keeping the workspace ready."],
        )

    def _refresh_approval_panel(self, session_dir: Path) -> None:
        approval = self.sessions.load_destructive_approval(session_dir)
        flash_plan = self.sessions.load_flash_plan(session_dir)
        if not self.confirmation_input.hasFocus():
            if approval.confirmation_phrase:
                self.confirmation_input.setText(approval.confirmation_phrase)
            else:
                self.confirmation_input.clear()
        if not self.restore_confirm_check.hasFocus():
            self.restore_confirm_check.setChecked(approval.restore_path_confirmed)
        if not self.approval_notes.hasFocus():
            self.approval_notes.setPlainText(approval.notes)

        if flash_plan is None:
            self.approval_status.setText(
                "No flash plan has been generated for this session yet. Complete assessment and planning first."
            )
            self._set_text_preserve_scroll(self.flash_plan_text, "No flash plan available.")
            return

        live_mode_text = (
            "enabled by policy" if self.policy.allow_live_destructive_actions else "blocked by policy"
        )
        approval_text = "approved" if approval.approved else "not approved"
        phrase_text = "ok" if approval.confirmation_phrase == "WIPE_AND_REBUILD" else "missing"
        backup_plan_path = session_dir / "backup" / "backup-plan.json"
        backup_plan = json.loads(backup_plan_path.read_text()) if backup_plan_path.exists() else {}
        self.approval_status.setText(
            f"Approval state: {approval_text}. Live destructive execution is currently {live_mode_text}."
        )
        lines = [
            f"Build path: {flash_plan.build_path}",
            f"Transport: {flash_plan.transport}",
            f"Restore path available: {flash_plan.restore_path_available}",
            f"Requires unlock: {flash_plan.requires_unlock}",
            f"Requires wipe: {flash_plan.requires_wipe}",
            f"Default mode: {'dry run' if flash_plan.dry_run else 'live'}",
            f"Confirmation phrase: {phrase_text}",
            f"Backup bundle captured: {'yes' if backup_plan else 'no'}",
            f"Step count: {flash_plan.step_count}",
            "",
            "Backup and restore:",
        ]
        if backup_plan:
            lines.extend(
                [
                    f"- bundle: {backup_plan.get('backup_bundle_path', 'unknown')}",
                    f"- metadata: {backup_plan.get('metadata_backup_path', 'unknown')}",
                    f"- restore feasible: {backup_plan.get('restore_path_feasible')}",
                    f"- notes: {backup_plan.get('restore_notes', 'No restore notes available.')}",
                    "",
                ]
            )
        else:
            lines.extend(["- No backup bundle exists yet.", ""])
        lines.extend(
            [
            "Planned steps:",
            ]
        )
        lines.extend(
            f"- {step.get('name', 'unknown')}: {step.get('description', '')}"
            for step in flash_plan.steps
        )
        self._set_text_preserve_scroll(self.flash_plan_text, "\n".join(lines))

    def _update_card_visibility(
        self,
        has_session: bool,
        usb_only_device: bool,
        engagement_status: str,
    ) -> None:
        show_connection_help = usb_only_device or engagement_status in {"usb_only_detected", "awaiting_user_approval"}
        self.connection_help_card.setVisible(show_connection_help)
        self.approval_card.setVisible(has_session)
        self.profile_card.setVisible(has_session)

    def _update_refresh_status(self, reason: str, has_live_device: bool, has_usb_only: bool) -> None:
        timestamp = utc_now().split("T", 1)[1].split(".", 1)[0]
        if has_live_device:
            state = "live device detected"
        elif has_usb_only:
            state = "usb phone seen, waiting for adb/fastboot"
        elif self.current_session_dir:
            state = "showing latest saved session"
        else:
            state = "waiting for phone"
        self.status_label.setText(f"Refresh status: {reason} at {timestamp} | {state}")
        self.logger.info("GUI refresh: reason=%s state=%s", reason, state)

    def manual_refresh(self) -> None:
        self.refresh_ui("Manual refresh")

    def _auto_refresh(self) -> None:
        self.refresh_ui("Auto refresh")

    def _apply_layout_mode(self, mode: str) -> None:
        self.layout_mode = mode
        while self.content_grid.count():
            self.content_grid.takeAt(0)

        if mode == "narrow":
            self.content_grid.addWidget(self.now_card, 0, 0)
            self.content_grid.addWidget(self.host_card, 1, 0)
            self.content_grid.addWidget(self.profile_card, 2, 0)
            self.content_grid.addWidget(self.connection_help_card, 3, 0)
            self.content_grid.addWidget(self.approval_card, 4, 0)
            self.content_grid.addWidget(self.steps_card, 5, 0)
            self.content_grid.addWidget(self.autonomous_card, 6, 0)
            self.content_grid.addWidget(self.device_card, 7, 0)
            self.content_grid.addWidget(self.help_card, 8, 0)
            self.content_grid.setColumnStretch(0, 1)
            self.content_grid.setColumnStretch(1, 0)
        else:
            self.content_grid.addWidget(self.now_card, 0, 0)
            self.content_grid.addWidget(self.steps_card, 0, 1, 2, 1)
            self.content_grid.addWidget(self.host_card, 1, 0)
            self.content_grid.addWidget(self.profile_card, 2, 0)
            self.content_grid.addWidget(self.connection_help_card, 2, 1)
            self.content_grid.addWidget(self.approval_card, 3, 1)
            self.content_grid.addWidget(self.autonomous_card, 4, 1)
            self.content_grid.addWidget(self.device_card, 3, 0, 2, 1)
            self.content_grid.addWidget(self.help_card, 5, 1)
            self.content_grid.setColumnStretch(0, 5)
            self.content_grid.setColumnStretch(1, 4)
        self.content_grid.setRowStretch(0, 0)
        self.content_grid.setRowStretch(1, 0)
        self.content_grid.setRowStretch(2, 1)

    def _handle_resize(self, event) -> None:
        width = self.window.width()
        desired_mode = "narrow" if width < 1080 else "wide"
        if desired_mode != self.layout_mode:
            self._apply_layout_mode(desired_mode)
        if width < 980:
            self.button_col.setDirection(QVBoxLayout.Direction.TopToBottom)
        else:
            self.button_col.setDirection(QHBoxLayout.Direction.LeftToRight)
        QMainWindow.resizeEvent(self.window, event)

    def _open_path(self, path: Path) -> None:
        subprocess.Popen(["xdg-open", str(path)])

    def _open_current_session(self, code: bool = False) -> None:
        if not self.current_session_dir:
            return
        if code:
            subprocess.Popen(["code", str(self.current_session_dir)])
        else:
            self._open_path(self.current_session_dir)

    def run(self) -> None:
        self.window.show()
        self.qt_app.exec()

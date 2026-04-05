from __future__ import annotations

import json
import logging
import subprocess
import sys
from time import monotonic
from pathlib import Path
from typing import Any

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
    AutonomyLimit,
    GoogleServicesPreference,
    PriorityFocus,
    RestoreExpectation,
    RiskTolerance,
    TechnicalComfort,
    UseCaseCategory,
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
        self.show_advanced = False
        self.last_live_sync_at = 0.0
        self.profile_form_dirty = False
        self.profile_form_syncing = False
        self.profile_form_session: Path | None = None

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
        self.timer.start(12000)
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
        QPushButton:disabled {
            background: #5a6473;
            color: #d0d7e3;
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
            "Runtime control surface for device rehabilitation, approvals, evidence, and recovery"
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
        self.advanced_toggle = QCheckBox("Show Advanced Details")
        self.advanced_toggle.toggled.connect(self._toggle_advanced_mode)
        button_col.addWidget(self.advanced_toggle)
        layout.addLayout(button_col)
        return box

    def _build_now_what_card(self) -> QGroupBox:
        group = QGroupBox("Runtime Mission")
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
        group = QGroupBox("Runtime Worker Queue")
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
        group = QGroupBox("1. Intake And Autonomy Limits")
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

        self.autonomy_combo = QComboBox()
        self.autonomy_combo.addItem("Conservative autonomy", AutonomyLimit.CONSERVATIVE.value)
        self.autonomy_combo.addItem("Balanced autonomy", AutonomyLimit.BALANCED.value)
        self.autonomy_combo.addItem("Agentic autonomy", AutonomyLimit.AGENTIC.value)

        self.risk_combo = QComboBox()
        self.risk_combo.addItem("Low risk tolerance", RiskTolerance.LOW.value)
        self.risk_combo.addItem("Medium risk tolerance", RiskTolerance.MEDIUM.value)
        self.risk_combo.addItem("High risk tolerance", RiskTolerance.HIGH.value)

        self.restore_combo = QComboBox()
        self.restore_combo.addItem("One-click restore preferred", RestoreExpectation.MUST_BE_ONE_CLICK.value)
        self.restore_combo.addItem("Guided restore is okay", RestoreExpectation.GUIDED_IS_OK.value)
        self.restore_combo.addItem("Research-first restore path is acceptable", RestoreExpectation.RESEARCH_OK.value)

        self.use_case_combo = QComboBox()
        for label, value in [
            ("Accessibility-focused phone", UseCaseCategory.ACCESSIBILITY.value),
            ("Kid-safe communication", UseCaseCategory.KID_SAFE.value),
            ("Media device", UseCaseCategory.MEDIA.value),
            ("Offline utility tool", UseCaseCategory.OFFLINE_UTILITY.value),
            ("Home control panel", UseCaseCategory.HOME_CONTROL.value),
            ("Lightweight custom Android", UseCaseCategory.LIGHTWEIGHT_ANDROID.value),
            ("Experimental hybrid path", UseCaseCategory.EXPERIMENTAL.value),
            ("Special-purpose terminal", UseCaseCategory.KIOSK.value),
        ]:
            self.use_case_combo.addItem(label, value)

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
            ("Autonomy limit", self.autonomy_combo),
            ("Acceptable risk tolerance", self.risk_combo),
            ("Restore expectation", self.restore_combo),
            ("Target use case category", self.use_case_combo),
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
        self._bind_profile_form_signals()
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
        group = QGroupBox("Install Gate")
        layout = QVBoxLayout(group)

        self.approval_status = QLabel(
            "This panel stays inactive until ForgeOS finishes research, preview, verification, and install preparation."
        )
        self.approval_status.setWordWrap(True)
        self.approval_status.setProperty("role", "body")
        layout.addWidget(self.approval_status)

        self.restore_confirm_check = QCheckBox("I confirm the restore path has been reviewed")
        layout.addWidget(self.restore_confirm_check)

        phrase_label = QLabel("Type WIPE_AND_REBUILD only when ForgeOS says install is ready")
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
        self.approve_button = QPushButton("Record Install Approval")
        self.approve_button.clicked.connect(self.record_wipe_approval)
        self.dry_run_button = QPushButton("Run Approved Dry Run")
        self.dry_run_button.clicked.connect(lambda: self.execute_flash(live_mode=False))
        self.live_button = QPushButton("Run Live Wipe And Flash")
        self.live_button.clicked.connect(lambda: self.execute_flash(live_mode=True))
        buttons.addWidget(self.approve_button)
        buttons.addWidget(self.dry_run_button)
        buttons.addWidget(self.live_button)
        layout.addLayout(buttons)

        self.flash_plan_text = QTextEdit()
        self.flash_plan_text.setReadOnly(True)
        layout.addWidget(self.flash_plan_text, 1)
        return group

    def _build_help_card(self) -> QGroupBox:
        group = QGroupBox("Artifacts")
        layout = QVBoxLayout(group)
        self.help_buttons: dict[str, QPushButton] = {}
        for key, label, path in [
            ("guide", "Open User Guide", self.project_root / "USER_GUIDE.md"),
            ("session", "Open Session Folder", self.project_root / "devices"),
            ("backup", "Open Session Backup", self.project_root / "devices"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, p=path: self._open_path(p))
            self.help_buttons[key] = button
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

    def _toggle_advanced_mode(self, checked: bool) -> None:
        self.show_advanced = checked
        self.refresh_ui("Advanced view changed")

    def _mark_profile_form_dirty(self, *_args: object) -> None:
        if self.profile_form_syncing:
            return
        self.profile_form_dirty = True

    def _bind_profile_form_signals(self) -> None:
        for combo in [
            self.persona_combo,
            self.comfort_combo,
            self.priority_combo,
            self.google_combo,
            self.autonomy_combo,
            self.risk_combo,
            self.restore_combo,
            self.use_case_combo,
            self.secondary_goal_combo,
        ]:
            combo.currentIndexChanged.connect(self._mark_profile_form_dirty)
        for checkbox in [
            self.updates_check,
            self.battery_check,
            self.lockdown_check,
        ]:
            checkbox.toggled.connect(self._mark_profile_form_dirty)

    def _interaction_in_progress(self) -> bool:
        focus = self.qt_app.focusWidget()
        return isinstance(focus, (QComboBox, QLineEdit, QTextEdit, QCheckBox, QPushButton))

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

    def _read_json(self, path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
        if not path.exists():
            return default or {}
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            self.logger.exception("Failed reading JSON from %s", path)
            return default or {}

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

    def _sync_live_session_evidence(self, session_dir: Path) -> None:
        profile_model = self.sessions.load_device_profile(session_dir)
        serial = profile_model.serial or ""
        if not serial:
            return
        active_adb = {device.get("serial") for device in adb.list_devices()}
        if serial not in active_adb:
            return

        live_profile = adb.describe_device(serial)
        hardware = adb.hardware_snapshot(serial)
        changed = False
        for key in ["manufacturer", "model", "android_version", "device_codename"]:
            value = live_profile.get(key)
            current = getattr(profile_model, key)
            if value and value != "Unknown" and value != current:
                setattr(profile_model, key, value)
                changed = True
        live_transport = live_profile.get("transport", profile_model.transport.value)
        if live_transport != profile_model.transport.value:
            changed = True
        profile_model.transport = profile_model.transport.__class__(live_transport)
        profile_model.raw_probe_data |= {
            **live_profile,
            "hardware_snapshot": hardware,
            "raw_event": {
                **profile_model.raw_probe_data.get("raw_event", {}),
                **live_profile,
            },
        }
        self.sessions.write_device_profile(session_dir, profile_model)

        device_payload = {
            "manufacturer": profile_model.manufacturer,
            "model": profile_model.model,
            "serial": profile_model.serial,
            "android_version": profile_model.android_version,
            "bootloader_locked": profile_model.bootloader_locked,
            "verified_boot_state": hardware.get("verified_boot_state") or profile_model.verified_boot_state,
            "slot_info": {
                "boot_slot": hardware.get("boot_slot", ""),
                "dynamic_partitions": hardware.get("dynamic_partitions", ""),
            },
            "battery": {"raw_dump": hardware.get("battery_dump", "")},
            "transport": profile_model.transport,
            "reachability": "adb-visible",
            "device_codename": profile_model.device_codename,
            "raw_event": profile_model.raw_probe_data.get("raw_event", {}),
        }
        assessment = self.orchestrator.assessor.execute({"device": device_payload, "session_dir": str(session_dir)})
        engagement = self.orchestrator.autonomous_engagement.execute({"device": device_payload, "session_dir": str(session_dir)})
        backup_plan = self.orchestrator.backup_restore.execute(
            {
                "device": device_payload,
                "session_dir": str(session_dir),
                "assessment": assessment,
            }
        )
        restore_plan = self.orchestrator.restore_controller.execute(
            {
                "session_dir": str(session_dir),
                "backup_plan": backup_plan["plan"],
            }
        )
        self.orchestrator.reports.write_session_report(
            session_dir,
            report_type="assessment",
            status=assessment["support_status"],
            summary=assessment["summary"],
            details={
                "event": device_payload.get("raw_event", {}),
                "assessment": assessment,
                "engagement": engagement,
                "live_hardware": hardware,
                "backup_plan": backup_plan["plan"],
                "restore_plan_path": restore_plan["restore_plan_path"],
            },
        )
        self.orchestrator.reports.write_session_report(
            session_dir,
            report_type="engagement",
            status=engagement["engagement_status"],
            summary=engagement["summary"],
            details=engagement,
        )
        self.orchestrator.reports.write_session_report(
            session_dir,
            report_type="backup_plan",
            status="captured" if backup_plan["restore_path_feasible"] else "limited",
            summary=backup_plan["plan"]["summary"],
            details=backup_plan["plan"],
        )
        self.orchestrator.reports.write_session_report(
            session_dir,
            report_type="restore_plan",
            status=restore_plan["status"],
            summary=restore_plan["summary"],
            details=restore_plan["details"],
        )
        state_model = self.sessions.load_session_state(session_dir)
        if assessment["support_status"] != state_model.support_status.value:
            state_model.support_status = state_model.support_status.__class__(assessment["support_status"])
            changed = True
        if engagement["engagement_status"] == "adb_connected" and state_model.current_blocker_type == "physical_action_blocker":
            state_model.current_blocker_type = "approval_or_external_artifact"
            changed = True
        if changed:
            self.sessions.write_session_state(session_dir, state_model)
        runtime_plan_path = session_dir / "runtime" / "session-plan.json"
        if changed or not runtime_plan_path.exists():
            self.orchestrator.recompute_session_runtime(session_dir, lightweight=True)

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
        host = details.get("host_capabilities", {})
        lines = [
            f"VS Code CLI: {'ready' if details.get('code_available') else 'missing'}",
            f"ADB: {'ready' if details.get('adb_available') else 'missing'}",
            f"Fastboot: {'ready' if details.get('fastboot_available') else 'missing'}",
            f"Goose: {'ready' if host.get('goose_ready') else 'limited'}",
            f"Aider: {'ready' if host.get('aider_ready') else 'limited'}",
            f"Ollama: {'ready' if host.get('ollama_model_available') else 'limited'}",
            f"Android emulator: {'ready' if host.get('emulator_available') and host.get('available_avds') else 'limited'}",
            f"Local model: {host.get('local_model', 'unknown')}",
            f"udev support: {'present' if details.get('udev_present') else 'missing'}",
            f"Workspace file: {details.get('workspace_file')}",
        ]
        if details.get("adb_available") and details.get("fastboot_available") and host.get("goose_ready"):
            summary = "This computer is ready for guided device assessment and local worker execution."
        else:
            summary = (
                "ForgeOS can start, but missing transport or local-worker capabilities will limit autonomous execution depth. "
                "Install or configure the missing tools and model providers to unlock the full runtime."
            )
        return "\n".join(lines), summary

    def _hardware_summary_lines(self, session_dir: Path, profile: dict[str, Any], assessment_report: dict[str, Any]) -> list[str]:
        raw_probe = profile.get("raw_probe_data", {})
        hardware = raw_probe.get("hardware_snapshot", {})
        slot_info = profile.get("slot_info") or {}
        battery = profile.get("battery") or {}
        lines = [
            f"- device codename: {profile.get('device_codename') or raw_probe.get('raw_event', {}).get('device_codename') or 'unknown'}",
            f"- product/board: {raw_probe.get('raw_event', {}).get('product') or hardware.get('board') or 'unknown'}",
            f"- hardware id: {hardware.get('hardware') or 'unknown'}",
            f"- cpu abi: {hardware.get('abi') or 'unknown'}",
            f"- boot slot: {slot_info.get('boot_slot') or hardware.get('boot_slot') or 'unknown'}",
            f"- dynamic partitions: {slot_info.get('dynamic_partitions') or hardware.get('dynamic_partitions') or 'unknown'}",
            f"- security patch: {hardware.get('security_patch') or 'unknown'}",
        ]
        if battery.get("raw_dump") or hardware.get("battery_dump"):
            lines.append("- battery telemetry: captured")
        partition_probe = self._read_json(session_dir / "raw" / "partition-probe.json")
        if partition_probe:
            lines.append("- partition probe: captured")
        elif assessment_report.get("details", {}).get("live_hardware"):
            lines.append("- live hardware snapshot: captured")
        else:
            lines.append("- partition probe: not captured yet")
        return lines

    def _backup_status_lines(self, session_dir: Path) -> list[str]:
        backup_plan = self._read_json(session_dir / "backup" / "backup-plan.json")
        restore_plan = self._read_json(session_dir / "restore" / "restore-plan.json")
        metadata = self._read_json(session_dir / "backup" / "device-metadata-backup.json")
        bundle_exists = bool(backup_plan)
        metadata_ok = bool(metadata.get("adb_metadata_available"))
        lines = [
            f"- host recovery bundle: {'ready' if bundle_exists else 'missing'}",
            f"- live device metadata backup: {'ready' if metadata_ok else 'partial'}",
            f"- restore plan: {'ready' if restore_plan else 'missing'}",
            f"- restore feasible: {backup_plan.get('restore_path_feasible', False)}",
        ]
        if backup_plan.get("backup_bundle_path"):
            lines.append(f"- bundle path: {backup_plan['backup_bundle_path']}")
        limitations = metadata.get("limitations") or backup_plan.get("limitations") or []
        if limitations:
            lines.append(f"- limitation: {limitations[0]}")
        return lines

    def _next_operator_action(
        self,
        profile: dict[str, Any],
        engagement_status: str,
        backup_plan: dict[str, Any],
        metadata_backup: dict[str, Any],
        approval: dict[str, Any],
        flash_plan_available: bool,
        runtime_plan: dict[str, Any] | None,
        playbook: dict[str, object] | None,
    ) -> str:
        runtime_plan = runtime_plan or {}
        manufacturer = profile.get("manufacturer") or "device"
        model = profile.get("model") or ""
        device_name = f"{manufacturer} {model}".strip()
        phase = runtime_plan.get("phase", "unknown")
        if engagement_status == "usb_only_detected":
            steps = list((playbook or {}).get("steps", []))[:2]
            return " ".join(steps) if steps else f"Unlock the {device_name}, enable USB debugging, and approve the trust prompt."
        if engagement_status == "awaiting_user_approval":
            return f"Unlock the {device_name} and approve the USB debugging trust prompt."
        if phase in {"deep_scan", "guided_access_enablement"}:
            return "Keep the phone connected while ForgeOS deep-scans the device and gathers transport and hardware evidence."
        if phase == "recommendation":
            return "Wait while ForgeOS turns the device evidence and your profile into a recommended rehabilitation path."
        if phase == "backup_restore":
            return "Wait while ForgeOS finalizes backup and restore readiness before any install work is considered."
        if phase == "build_preview":
            return "Wait while ForgeOS generates and records the preview path for the proposed build."
        if phase == "interactive_verification":
            return "Review the verification output and expected limitations before any destructive install step is considered."
        if phase == "wipe_install" and not approval.get("approved"):
            return "Review the install plan and restore notes, then approve install only if you want ForgeOS to proceed."
        if not backup_plan:
            return "Wait while ForgeOS finishes the host recovery bundle."
        if not metadata_backup.get("adb_metadata_available"):
            return "Keep the phone unlocked and connected while ForgeOS retries the live device metadata backup."
        if not flash_plan_available:
            return "Wait while ForgeOS finishes the current research and planning stage."
        if not approval.get("approved"):
            return "Approval is not needed yet unless ForgeOS explicitly moves the session into install readiness."
        return "Click Run Approved Dry Run to rehearse the wipe-and-flash plan without touching the phone."

    def _phase_copy(
        self,
        runtime_plan: dict[str, Any],
        support: str,
        backup_ready: bool,
        metadata_ready: bool,
        blocker_summary: str,
    ) -> tuple[str, str, str]:
        phase = runtime_plan.get("phase", "unknown")
        recommended_path = runtime_plan.get("recommended_path", "research_only_path")
        recommended_use_case = runtime_plan.get("recommended_use_case", "unknown")

        if phase in {"guided_access_enablement", "deep_scan"}:
            return (
                "ForgeOS is actively assessing the connected device.",
                "Deep scan is in progress. ForgeOS is gathering transport, hardware, and system evidence before making any build decision.",
                "Collecting live device evidence, updating the assessment, and holding all destructive work behind the evidence gate.",
            )
        if phase == "recommendation":
            summary = (
                f"Research is in progress. ForgeOS is comparing device evidence and your profile to choose the best attainable outcome. "
                f"Current recommendation: {recommended_use_case.replace('_', ' ')}."
            )
            if recommended_path == "research_only_path":
                summary += " Install planning stays deferred until transport and feasibility improve."
            return (
                "ForgeOS is researching the best rehabilitation path.",
                summary,
                "Reviewing support evidence, scoring attainable use cases, and deferring wipe/install until the path is credible.",
            )
        if phase == "backup_restore":
            return (
                "ForgeOS is preparing backup and restore readiness.",
                f"Assessment status is {support}. Restore evidence is {'ready' if backup_ready else 'still being built'}, and live metadata is {'ready' if metadata_ready else 'still improving'}.",
                "Recording the host recovery bundle, restore notes, and rollback evidence before any later-stage build work.",
            )
        if phase == "build_preview":
            return (
                "ForgeOS is generating a preview of the proposed build.",
                "The runtime has a candidate path and is building preview artifacts before install is even considered.",
                "Producing preview output, preserving restore visibility, and keeping install gated.",
            )
        if phase == "interactive_verification":
            return (
                "ForgeOS is verifying the proposed outcome.",
                "Preview and verification are underway so the user can inspect limitations and recovery assumptions before any wipe/install decision.",
                "Running verification checkpoints and collecting operator-facing review items.",
            )
        if phase == "wipe_install":
            return (
                "ForgeOS has reached install review readiness.",
                "Research, preview, and verification are complete enough for an operator install decision. Wipe/install still requires explicit approval.",
                "Holding the destructive plan behind the install gate and waiting for operator review.",
            )
        return (
            f"ForgeOS is tracking the current session state: {phase}.",
            f"Assessment status is {support}. Restore evidence is {'ready' if backup_ready else 'still being built'}, and live metadata is {'ready' if metadata_ready else 'still improving'}.",
            f"Tracking the next blocker and keeping the session current. Current blocker: {blocker_summary}",
        )

    def _format_device_text(self, session_dir: Path) -> str:
        profile_path = session_dir / "device-profile.json"
        state_path = session_dir / "session-state.json"
        report_path = session_dir / "reports" / "assessment.json"
        engagement_path = session_dir / "reports" / "engagement.json"
        runtime_plan_path = session_dir / "runtime" / "session-plan.json"

        profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        engagement = json.loads(engagement_path.read_text()) if engagement_path.exists() else {}
        runtime_plan = json.loads(runtime_plan_path.read_text()) if runtime_plan_path.exists() else {}
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

        if runtime_plan:
            lines.extend(
                [
                    "",
                    "Runtime session plan:",
                    f"- phase: {runtime_plan.get('phase', 'unknown')}",
                    f"- recommended use case: {runtime_plan.get('recommended_use_case', 'unknown')}",
                    f"- recommended path: {runtime_plan.get('recommended_path', 'unknown')}",
                ]
            )

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

        assessment = report.get("details", {}).get("assessment", {})
        if assessment:
            lines.extend(
                [
                    "",
                    "Assessment status:",
                    f"- support: {assessment.get('support_status', 'unknown')}",
                    f"- restore feasible: {assessment.get('restore_path_feasible', 'unknown')}",
                    f"- recommended path: {assessment.get('recommended_path', 'unknown')}",
                ]
            )

        lines.extend(["", "Hardware assessment:"])
        lines.extend(self._hardware_summary_lines(session_dir, profile, report))

        lines.extend(["", "Backup and restore readiness:"])
        lines.extend(self._backup_status_lines(session_dir))

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
        runtime_plan_path = session_dir / "runtime" / "session-plan.json"
        worker_routing_path = session_dir / "runtime" / "worker-routing.json"
        if not engagement_path.exists():
            return (
                "No autonomous engagement report yet.",
                "ForgeOS has not recorded any autonomous engagement attempts for this session yet.",
            )

        engagement = json.loads(engagement_path.read_text())
        blocker = json.loads(blocker_path.read_text()) if blocker_path.exists() else {}
        build_plan = json.loads(build_plan_path.read_text()) if build_plan_path.exists() else {}
        execution_queue = json.loads(execution_queue_path.read_text()) if execution_queue_path.exists() else {}
        runtime_plan = json.loads(runtime_plan_path.read_text()) if runtime_plan_path.exists() else {}
        worker_routing = json.loads(worker_routing_path.read_text()) if worker_routing_path.exists() else {}
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

        if runtime_plan:
            lines.extend(
                [
                    "",
                    "Runtime plan:",
                    f"- phase: {runtime_plan.get('phase', 'unknown')}",
                    f"- recommended use case: {runtime_plan.get('recommended_use_case', 'unknown')}",
                    f"- operator summary: {runtime_plan.get('operator_summary', 'No runtime summary available')}",
                ]
            )

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

        routes = worker_routing.get("routes") or []
        if routes:
            lines.extend(["", "Worker routing:"])
            for route in routes[:4]:
                lines.append(
                    f"- {route.get('task_type', 'unknown')}: {route.get('selected_worker', 'unknown')} via `{route.get('adapter_name', 'unknown')}`"
                )

        executions = worker_routing.get("executions") or []
        if executions:
            lines.extend(["", "Worker execution:"])
            for execution in executions[:4]:
                lines.append(
                    f"- {execution.get('task_type', 'unknown')}: {execution.get('status', 'unknown')} with confidence {execution.get('confidence', 0)}"
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
        if self.profile_form_dirty and self.profile_form_session == session_dir:
            return
        profile = self.sessions.load_user_profile(session_dir)
        goals = self.sessions.load_os_goals(session_dir)
        self.profile_form_syncing = True
        try:
            self._set_combo_by_value(self.persona_combo, profile.persona.value)
            self._set_combo_by_value(self.comfort_combo, profile.technical_comfort.value)
            self._set_combo_by_value(self.priority_combo, profile.primary_priority.value)
            self._set_combo_by_value(self.google_combo, profile.google_services_preference.value)
            self._set_combo_by_value(self.autonomy_combo, profile.autonomy_limit.value)
            self._set_combo_by_value(self.risk_combo, profile.risk_tolerance.value)
            self._set_combo_by_value(self.restore_combo, profile.restore_expectation.value)
            self._set_combo_by_value(self.use_case_combo, profile.target_use_case.value)
            self._set_combo_by_value(self.secondary_goal_combo, goals.secondary_goal.value)
            self.updates_check.setChecked(goals.requires_reliable_updates)
            self.battery_check.setChecked(goals.prefers_long_battery_life)
            self.lockdown_check.setChecked(goals.prefers_lockdown_defaults)
        finally:
            self.profile_form_syncing = False
        self.profile_form_dirty = False
        self.profile_form_session = session_dir

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
        user_profile.autonomy_limit = AutonomyLimit(self.autonomy_combo.currentData())
        user_profile.risk_tolerance = RiskTolerance(self.risk_combo.currentData())
        user_profile.restore_expectation = RestoreExpectation(self.restore_combo.currentData())
        user_profile.target_use_case = UseCaseCategory(self.use_case_combo.currentData())
        self.sessions.write_user_profile(self.current_session_dir, user_profile)

        os_goals = self.sessions.load_os_goals(self.current_session_dir)
        os_goals.top_goal = PriorityFocus(self.priority_combo.currentData())
        os_goals.secondary_goal = PriorityFocus(self.secondary_goal_combo.currentData())
        os_goals.requires_reliable_updates = self.updates_check.isChecked()
        os_goals.prefers_long_battery_life = self.battery_check.isChecked()
        os_goals.prefers_lockdown_defaults = self.lockdown_check.isChecked()
        self.sessions.write_os_goals(self.current_session_dir, os_goals)
        self.profile_form_dirty = False
        self.profile_form_session = self.current_session_dir

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
                    "autonomy_limit": user_profile.autonomy_limit.value,
                    "risk_tolerance": user_profile.risk_tolerance.value,
                    "restore_expectation": user_profile.restore_expectation.value,
                    "target_use_case": user_profile.target_use_case.value,
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
        self.orchestrator.recompute_session_runtime(self.current_session_dir, lightweight=True)
        self.profile_status.setText(
            f"Saved profile. ForgeOS is refreshing the recommendation and safety plan for `{strategy['strategy_id']}` without starting heavy worker execution."
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
                    next_action=self._next_operator_action(
                        {
                            "manufacturer": usb_only_device.get("vendor_hint"),
                            "model": "phone",
                        },
                        "usb_only_detected",
                        {},
                        {},
                        {"approved": False},
                        False,
                        {"phase": "guided_access_enablement"},
                        playbook,
                    ),
                )
                title, checklist, agent_status = self._build_execution_checklist(
                    profile={
                        "manufacturer": usb_only_device.get("vendor_hint"),
                        "model": "phone",
                    },
                    state={"state": "QUESTION_GATE", "support_status": "research_only"},
                    runtime_plan={"phase": "guided_access_enablement"},
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
                    next_action="Connect one Android phone with a good USB data cable and unlock it if Android is booted.",
                )
                title, checklist, agent_status = self._build_execution_checklist(
                    profile=None,
                    state=None,
                    runtime_plan=None,
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
        should_sync_live_session = False
        if live_session:
            now = monotonic()
            if reason != "Auto refresh":
                should_sync_live_session = True
            elif not self._interaction_in_progress() and (now - self.last_live_sync_at) >= 30:
                should_sync_live_session = True
        if should_sync_live_session and live_session:
            self._sync_live_session_evidence(self.current_session_dir)
            self.last_live_sync_at = monotonic()
        state = json.loads((self.current_session_dir / "session-state.json").read_text())
        profile = json.loads((self.current_session_dir / "device-profile.json").read_text())
        engagement_path = self.current_session_dir / "reports" / "engagement.json"
        engagement_report = json.loads(engagement_path.read_text()) if engagement_path.exists() else {}
        engagement_status = engagement_report.get("status", engagement_report.get("engagement_status", "unknown"))
        assessment_report = self._read_json(self.current_session_dir / "reports" / "assessment.json")
        runtime_plan = self._read_json(self.current_session_dir / "runtime" / "session-plan.json")
        backup_plan = self._read_json(self.current_session_dir / "backup" / "backup-plan.json")
        metadata_backup = self._read_json(self.current_session_dir / "backup" / "device-metadata-backup.json")
        blocker_report = self._read_json(self.current_session_dir / "reports" / "blocker.json")
        playbook = self._playbook_for_context(
            profile.get("manufacturer"),
            profile.get("model"),
            engagement_status,
            profile.get("transport", "unknown"),
        )

        if live_session:
            support = assessment_report.get("details", {}).get("assessment", {}).get("support_status", state.get("support_status", "unknown"))
            metadata_ready = bool(metadata_backup.get("adb_metadata_available"))
            blocker_summary = blocker_report.get("summary") or "No active blocker summary yet."
            session_flash_plan = self.sessions.load_flash_plan(self.current_session_dir)
            approval = self.sessions.load_destructive_approval(self.current_session_dir)
            objective_title, objective_summary, agent_action = self._phase_copy(
                runtime_plan,
                support,
                bool(backup_plan),
                metadata_ready,
                blocker_summary,
            )
            next_action = self._next_operator_action(
                profile,
                engagement_status,
                backup_plan,
                metadata_backup,
                {"approved": approval.approved},
                bool(session_flash_plan),
                runtime_plan,
                playbook,
            )
            self._set_objective_panel(
                objective_title
                + " "
                + f"Live device: {profile.get('manufacturer') or 'Unknown'} {profile.get('model') or 'device'}"
                + (f" on Android {profile.get('android_version')}" if profile.get("android_version") else ""),
                objective_summary,
                playbook=playbook,
                agent_action=agent_action,
                next_action=next_action,
            )
        elif usb_only_device:
            self._set_objective_panel(
                f"{usb_only_device.get('vendor_hint')} phone connected, but still not in adb or fastboot.",
                "ForgeOS is showing the latest saved session for reference while it keeps retrying safe host-side engagement.",
                playbook=playbook,
                agent_action="Retrying adb engagement, watching for transport changes, and keeping the device session ready to resume automatically.",
                next_action=self._next_operator_action(profile, engagement_status, backup_plan, metadata_backup, {"approved": False}, False, runtime_plan, playbook),
            )
        else:
            latest_profile = json.loads((latest_saved / "device-profile.json").read_text())
            self._set_objective_panel(
                "No phone is currently connected.",
                f"ForgeOS is showing the latest saved session for {latest_profile.get('manufacturer') or 'Unknown'} "
                f"{latest_profile.get('model') or 'device'} while waiting for a live device.",
                agent_action="Keeping the last session available for reference and waiting for the next real device event.",
                next_action="Reconnect the phone when you are ready to continue.",
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
        session_flash_plan = self.sessions.load_flash_plan(self.current_session_dir)
        approval = self.sessions.load_destructive_approval(self.current_session_dir)
        checklist_title, checklist, agent_status = self._build_execution_checklist(
            profile=profile,
            state=state,
            runtime_plan=runtime_plan,
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
        playbook_steps = list(playbook.get("steps", []))
        lines = [
            playbook["summary"],
            "",
            "Operator steps:",
        ]
        if playbook_steps:
            lines.extend(f"- {step}" for step in playbook_steps)
            lines.append("")
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
        lines.extend(f"- {step}" for step in playbook_steps)
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
        next_action: str | None = None,
    ) -> None:
        self.primary_label.setText(headline)
        self.secondary_label.setText(subheadline)
        if playbook:
            lines = [
                "ForgeOS is doing now:",
                f"- {agent_action or 'Watching USB, adb, and fastboot, retrying safe engagement, and updating the session automatically.'}",
                "",
                "You need to do next:",
            ]
            lines.append(f"- {next_action or 'Wait while ForgeOS continues the current runtime step.'}")
            self._set_text_preserve_scroll(self.objective_text, "\n".join(lines))
        else:
            self._set_text_preserve_scroll(
                self.objective_text,
                "\n".join(
                    [
                        "ForgeOS is doing now:",
                        f"- {agent_action or 'Waiting for a phone and keeping the workspace ready.'}",
                        "",
                        "You need to do next:",
                        f"- {next_action or 'Connect one Android phone with a good USB data cable and unlock it if Android is booted.'}",
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
            lines.extend(["What ForgeOS has already done:"])
            lines.extend(f"- {item}" for item in agent_status)
            lines.append("")
        lines.append("What happens next:")
        lines.extend(f"- {item}" for item in checklist)
        self._set_text_preserve_scroll(self.steps_text, "\n".join(lines))

    def _build_execution_checklist(
        self,
        profile: dict[str, object] | None,
        state: dict[str, object] | None,
        runtime_plan: dict[str, object] | None,
        engagement: dict[str, object] | None,
        playbook: dict[str, object] | None,
        flash_plan: dict[str, object] | None,
        backup_plan: dict[str, object] | None,
        approval: dict[str, object] | None,
        live_session: bool,
    ) -> tuple[str, list[str], list[str]]:
        profile = profile or {}
        state = state or {}
        runtime_plan = runtime_plan or {}
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
        phase = str(runtime_plan.get("phase", "unknown"))
        metadata_backup = self._read_json(self.current_session_dir / "backup" / "device-metadata-backup.json") if self.current_session_dir else {}
        backup_with_adb = bool(metadata_backup.get("adb_metadata_available"))

        agent_status = [
            f"Connected to the phone over {engagement_status.replace('_', ' ')}.",
            f"Assessment status is {support_status}.",
        ]
        if backup_plan:
            agent_status.append("The host recovery bundle is ready.")
        else:
            agent_status.append("ForgeOS is still preparing the host recovery bundle.")
        agent_status.append(
            "The live device metadata backup is ready." if backup_with_adb else "ForgeOS is still improving the live device metadata backup."
        )

        if engagement_status == "usb_only_detected":
            checklist = [
                "Unlock the phone and complete the connection steps shown in the connection panel.",
                "Wait for ForgeOS to detect adb, fastboot, or another manageable transport automatically.",
            ]
            return (
                f"Current stage for {manufacturer} {model}: connection setup",
                checklist,
                agent_status + [
                    "ForgeOS is retrying safe adb engagement and watching for a transport change."
                ],
            )

        if engagement_status == "awaiting_user_approval":
            checklist = [
                "Unlock the phone and approve the USB debugging trust prompt.",
                "Keep the phone unlocked until ForgeOS shows adb connected.",
            ]
            return (
                f"Current stage for {manufacturer} {model}: trust approval",
                checklist,
                agent_status + [
                    "ForgeOS is waiting only for the phone-side trust prompt."
                ],
            )

        if live_session and support_status in {"actionable", "research_only"}:
            phase_labels = {
                "deep_scan": "deep scan",
                "recommendation": "research and recommendation",
                "backup_restore": "backup and restore readiness",
                "build_preview": "preview generation",
                "interactive_verification": "interactive verification",
                "wipe_install": "install decision",
            }
            checklist: list[str] = []
            if phase in {"deep_scan", "guided_access_enablement"}:
                checklist.extend(
                    [
                        "Keep the phone connected and unlocked while ForgeOS collects hardware, transport, and partition evidence.",
                        "Wait for the assessment and recommendation outputs to update.",
                    ]
                )
            elif phase == "recommendation":
                checklist.extend(
                    [
                        "Wait while ForgeOS compares device evidence, your profile, and support data.",
                        "Review the recommended rehabilitation target when it appears.",
                    ]
                )
            elif phase == "backup_restore":
                checklist.extend(
                    [
                        "Wait for ForgeOS to capture backup and restore readiness before any install work is considered.",
                        "Keep the device connected so recovery evidence remains current.",
                    ]
                )
            elif phase in {"build_preview", "interactive_verification"}:
                checklist.extend(
                    [
                        "Review the preview and verification outputs for the proposed build path.",
                        "Confirm expected limitations and restore assumptions before install is considered.",
                    ]
                )
            elif phase == "wipe_install" and flash_plan and not approval.get("approved"):
                checklist.extend(
                    [
                        "Review the install plan and restore notes in the install panel.",
                        "Approve install only if you want ForgeOS to move from planning into destructive execution.",
                    ]
                )
            elif approval.get("approved"):
                checklist.append("Run an approved dry run first. Use live wipe and flash only when policy explicitly allows it.")
            else:
                checklist.append("ForgeOS has finished the current non-destructive preparation step.")
            return (
                f"Current stage for {manufacturer} {model}: {phase_labels.get(phase, state_name.replace('_', ' ').lower())}",
                checklist,
                agent_status + [
                    "No wipe or destructive flash has happened."
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
        runtime_plan = self._read_json(session_dir / "runtime" / "session-plan.json")
        phase = runtime_plan.get("phase", "unknown")
        approval_gates = runtime_plan.get("approval_gates", []) or []
        install_gate = next(
            (gate for gate in approval_gates if gate.get("action") == "wipe_and_install"),
            {},
        )
        install_ready = phase == "wipe_install" and flash_plan is not None and flash_plan.status != "deferred"
        review_visible = phase in {"interactive_verification", "wipe_install"}
        if not self.confirmation_input.hasFocus():
            if approval.confirmation_phrase:
                self.confirmation_input.setText(approval.confirmation_phrase)
            else:
                self.confirmation_input.clear()
        if not self.restore_confirm_check.hasFocus():
            self.restore_confirm_check.setChecked(approval.restore_path_confirmed)
        if not self.approval_notes.hasFocus():
            self.approval_notes.setPlainText(approval.notes)

        if flash_plan is None or flash_plan.status == "deferred" or not install_ready:
            if review_visible and flash_plan is not None and flash_plan.status != "deferred":
                self.approval_status.setText(
                    "Install review is visible now. You can pre-record approval details, but execution stays blocked until ForgeOS reaches install readiness."
                )
            else:
                self.approval_status.setText(
                    "Install approval is not active yet. ForgeOS is still in research, preview, verification, or non-destructive planning."
                )
            summary_lines = [
                f"Current runtime phase: {phase}",
                "",
                (
                    "You can review the install gate now, but dry run and live execution remain blocked until install readiness."
                    if review_visible and flash_plan is not None and flash_plan.status != "deferred"
                    else "Install approval stays hidden from the critical path until ForgeOS reaches install readiness."
                ),
            ]
            missing_requirements = install_gate.get("missing_requirements", [])
            if missing_requirements:
                summary_lines.extend(["", "Remaining install requirements:"])
                summary_lines.extend(f"- {item}" for item in missing_requirements)
            else:
                summary_lines.extend(
                    [
                        "",
                        "What ForgeOS should complete first:",
                        "- assessment and recommendation",
                        "- backup and restore readiness",
                        "- preview generation",
                        "- verification review",
                    ]
                )
            if flash_plan is not None:
                summary_lines.extend(
                    [
                        "",
                        f"Current install plan status: {flash_plan.status}",
                        f"Current build path: {flash_plan.build_path}",
                        flash_plan.summary,
                    ]
                )
            self._set_text_preserve_scroll(self.flash_plan_text, "\n".join(summary_lines))
            self.approve_button.setEnabled(bool(review_visible and flash_plan is not None and flash_plan.status != "deferred"))
            self.dry_run_button.setEnabled(False)
            self.live_button.setEnabled(False)
            return

        live_mode_text = (
            "enabled by policy" if self.policy.allow_live_destructive_actions else "blocked by policy"
        )
        approval_text = "approved" if approval.approved else "not approved"
        phrase_text = "ok" if approval.confirmation_phrase == "WIPE_AND_REBUILD" else "missing"
        backup_plan_path = session_dir / "backup" / "backup-plan.json"
        backup_plan = json.loads(backup_plan_path.read_text()) if backup_plan_path.exists() else {}
        metadata_backup_path = session_dir / "backup" / "device-metadata-backup.json"
        metadata_backup = self._read_json(metadata_backup_path)
        self.approval_status.setText(
            f"Approval state: {approval_text}. Live destructive execution is currently {live_mode_text}."
        )
        can_record_approval = bool(flash_plan) and install_ready
        can_dry_run = (
            bool(flash_plan)
            and approval.approved
            and approval.confirmation_phrase == "WIPE_AND_REBUILD"
            and approval.restore_path_confirmed
        )
        can_live = can_dry_run and self.policy.allow_live_destructive_actions
        self.approve_button.setEnabled(can_record_approval)
        self.dry_run_button.setEnabled(can_dry_run)
        self.live_button.setEnabled(can_live)
        lines = [
            f"Build path: {flash_plan.build_path}",
            f"Transport: {flash_plan.transport}",
            f"Restore path available: {flash_plan.restore_path_available}",
            f"Requires unlock: {flash_plan.requires_unlock}",
            f"Requires wipe: {flash_plan.requires_wipe}",
            f"Default mode: {'dry run' if flash_plan.dry_run else 'live'}",
            f"Confirmation phrase: {phrase_text}",
            f"Host recovery bundle captured: {'yes' if backup_plan else 'no'}",
            f"Live device metadata captured: {'yes' if metadata_backup.get('adb_metadata_available') else 'partial/no'}",
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
            if metadata_backup.get("limitations"):
                lines.extend([f"- live metadata limitation: {metadata_backup['limitations'][0]}", ""])
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
        runtime_plan = self._read_json(self.current_session_dir / "runtime" / "session-plan.json") if self.current_session_dir else {}
        phase = runtime_plan.get("phase", "unknown")
        flash_plan = self.sessions.load_flash_plan(self.current_session_dir) if self.current_session_dir else None
        install_visible = has_session and phase in {"interactive_verification", "wipe_install"} and flash_plan is not None and flash_plan.status != "deferred"
        show_connection_help = usb_only_device or engagement_status in {"usb_only_detected", "awaiting_user_approval"}
        self.connection_help_card.setVisible(show_connection_help)
        self.approval_card.setVisible(install_visible)
        self.profile_card.setVisible(has_session)
        self.help_card.setVisible(has_session or usb_only_device)
        self.device_card.setVisible(self.show_advanced and has_session)
        self.autonomous_card.setVisible(self.show_advanced and has_session)
        self.host_card.setVisible(self.show_advanced or not has_session)

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
            self.content_grid.addWidget(self.steps_card, 1, 0)
            self.content_grid.addWidget(self.host_card, 2, 0)
            self.content_grid.addWidget(self.profile_card, 3, 0)
            self.content_grid.addWidget(self.connection_help_card, 4, 0)
            self.content_grid.addWidget(self.device_card, 5, 0)
            self.content_grid.addWidget(self.autonomous_card, 6, 0)
            self.content_grid.addWidget(self.approval_card, 7, 0)
            self.content_grid.addWidget(self.help_card, 8, 0)
            self.content_grid.setColumnStretch(0, 1)
            self.content_grid.setColumnStretch(1, 0)
        else:
            self.content_grid.addWidget(self.now_card, 0, 0)
            self.content_grid.addWidget(self.host_card, 0, 1)
            self.content_grid.addWidget(self.profile_card, 1, 0)
            self.content_grid.addWidget(self.steps_card, 1, 1)
            self.content_grid.addWidget(self.connection_help_card, 2, 0)
            self.content_grid.addWidget(self.device_card, 2, 1)
            self.content_grid.addWidget(self.autonomous_card, 3, 0)
            self.content_grid.addWidget(self.help_card, 3, 1)
            self.content_grid.addWidget(self.approval_card, 4, 0, 1, 2)
            self.content_grid.setColumnStretch(0, 5)
            self.content_grid.setColumnStretch(1, 5)
        for row in range(6):
            self.content_grid.setRowStretch(row, 0)
        self.content_grid.setRowStretch(5, 1)

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

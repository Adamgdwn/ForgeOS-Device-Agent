from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.knowledge import KnowledgeEngine
from app.integrations import adb, fastboot, fastbootd


class ForgeControlApp:
    def __init__(self, root: Path, bootstrap_report: dict[str, object]) -> None:
        self.project_root = root
        self.bootstrap_report = bootstrap_report
        self.devices_dir = root / "devices"
        self.knowledge = KnowledgeEngine(root)
        self.current_session_dir: Path | None = None
        self.layout_mode = "wide"

        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setApplicationName("ForgeOS Device Agent")
        self.qt_app.setStyleSheet(self._stylesheet())

        self.window = QMainWindow()
        self.window.setWindowTitle("ForgeOS Device Agent")
        self.window.resize(1180, 760)
        self.window.setMinimumSize(860, 620)
        self.window.resizeEvent = self._handle_resize

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.window.setCentralWidget(scroll)

        central = QWidget()
        scroll.setWidget(central)
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
        self.device_card = self._build_device_card()
        self.help_card = self._build_help_card()
        self._apply_layout_mode("wide")

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_ui)
        self.timer.start(3000)
        self.refresh_ui()

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
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        layout.addLayout(text_col, 1)

        self.button_col = QHBoxLayout()
        button_col = self.button_col
        for label, callback in [
            ("Refresh", self.refresh_ui),
            ("Open User Guide", lambda: self._open_path(self.project_root / "USER_GUIDE.md")),
            ("Open Devices Folder", lambda: self._open_path(self.devices_dir)),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            button_col.addWidget(button)
        layout.addLayout(button_col)
        return box

    def _build_now_what_card(self) -> QGroupBox:
        group = QGroupBox("What To Do Now")
        layout = QVBoxLayout(group)
        self.primary_label = QLabel()
        self.primary_label.setWordWrap(True)
        self.primary_label.setProperty("role", "body")
        self.secondary_label = QLabel()
        self.secondary_label.setWordWrap(True)
        self.secondary_label.setProperty("role", "body")
        layout.addWidget(self.primary_label)
        layout.addWidget(self.secondary_label)
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

    def _build_steps_card(self) -> QGroupBox:
        group = QGroupBox("Guided Workflow")
        layout = QVBoxLayout(group)
        steps = [
            (
                "1. Launch ForgeOS and leave this window open.",
                "You do not need to use the terminal for normal first-time testing.",
            ),
            (
                "2. Connect one Android phone with a known-good USB data cable.",
                "Use one phone at a time while we validate the workflow.",
            ),
            (
                "3. If the phone is booted into Android, approve the USB debugging prompt on the device.",
                "If nothing appears within a few seconds, try another USB cable or reconnect the phone.",
            ),
            (
                "4. Wait for ForgeOS to create a new device session automatically.",
                "Each phone gets its own folder under devices/ so work does not mix together.",
            ),
            (
                "5. Read the session assessment before attempting any unlock or flash action.",
                "Inexperienced users should stay in assess-first mode until a device-specific plan is confirmed.",
            ),
            (
                "6. Stop if ForgeOS reports blocked, unknown transport, or no restore path.",
                "Safety and reversibility matter more than speed.",
            ),
        ]
        for title, hint in steps:
            block = QFrame()
            block.setProperty("role", "stepblock")
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(12, 12, 12, 12)
            step_label = QLabel(title)
            step_label.setWordWrap(True)
            step_label.setProperty("role", "body")
            hint_label = QLabel(hint)
            hint_label.setWordWrap(True)
            hint_label.setProperty("role", "hint")
            block_layout.addWidget(step_label)
            block_layout.addWidget(hint_label)
            layout.addWidget(block)
        layout.addStretch(1)
        return group

    def _build_help_card(self) -> QGroupBox:
        group = QGroupBox("Helpful Files")
        layout = QVBoxLayout(group)
        for label, path in [
            ("Open User Guide", self.project_root / "USER_GUIDE.md"),
            ("Open Master Policies", self.project_root / "master" / "policies"),
            ("Open Knowledge", self.project_root / "knowledge"),
            ("Open Promotion", self.project_root / "promotion"),
            ("Open Logs", self.project_root / "logs"),
            ("Open Output Reports", self.project_root / "output"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, p=path: self._open_path(p))
            layout.addWidget(button)
        layout.addStretch(1)
        return group

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

        profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
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

        notes = state.get("notes") or []
        if notes:
            lines.extend(["", "Recent notes:"])
            lines.extend(f"- {note}" for note in notes[-4:])
        return "\n".join(lines)

    def refresh_ui(self) -> None:
        sessions = self._collect_sessions()
        live_session = self._current_live_session(sessions)
        host_text, readiness = self._compose_host_status()
        self.host_label.setText(host_text)
        self.readiness_label.setText(readiness)

        latest_saved = sessions[0] if sessions else None

        if not latest_saved:
            self.current_session_dir = None
            self.primary_label.setText(
                "ForgeOS is ready. Connect one Android phone by USB and keep this window open."
            )
            self.secondary_label.setText(
                "If the phone is running Android, unlock it and approve the USB debugging prompt when asked. "
                "A new device session will appear automatically."
            )
            self.device_title.setText("No device session detected yet.")
            self.device_text.setPlainText(
                "Waiting for a phone.\n\n"
                "Recommended first test:\n"
                "- Start with a non-primary phone.\n"
                "- Use a reliable USB data cable.\n"
                "- Enable USB debugging if Android is booted.\n"
                "- Wait for a session folder to appear under devices/.\n"
            )
            self.open_folder_button.setEnabled(False)
            self.open_code_button.setEnabled(False)
            return

        self.current_session_dir = live_session or latest_saved
        state = json.loads((self.current_session_dir / "session-state.json").read_text())
        profile = json.loads((self.current_session_dir / "device-profile.json").read_text())

        if live_session:
            self.primary_label.setText(
                f"Device connected now: {profile.get('manufacturer') or 'Unknown'} {profile.get('model') or 'device'}."
            )
            self.secondary_label.setText(
                "Read the assessment summary below before doing anything destructive. "
                "If support is blocked or research-only, stop and review the restore path first."
            )
        else:
            latest_profile = json.loads((latest_saved / "device-profile.json").read_text())
            self.primary_label.setText(
                "No phone is currently connected. ForgeOS is showing the latest saved session for reference."
            )
            self.secondary_label.setText(
                f"Latest saved session: {latest_profile.get('manufacturer') or 'Unknown'} "
                f"{latest_profile.get('model') or 'device'}. Connect a real phone by USB to replace this view with a live session."
            )

        title_prefix = "Live session" if live_session else "Latest saved session"
        self.device_title.setText(
            f"{title_prefix}: {self.current_session_dir.name}  |  State: {state.get('state', 'unknown')}"
        )
        self.device_text.setPlainText(self._format_device_text(self.current_session_dir))
        self.open_folder_button.setEnabled(True)
        self.open_code_button.setEnabled(True)

    def _apply_layout_mode(self, mode: str) -> None:
        self.layout_mode = mode
        while self.content_grid.count():
            self.content_grid.takeAt(0)

        if mode == "narrow":
            self.content_grid.addWidget(self.now_card, 0, 0)
            self.content_grid.addWidget(self.host_card, 1, 0)
            self.content_grid.addWidget(self.steps_card, 2, 0)
            self.content_grid.addWidget(self.device_card, 3, 0)
            self.content_grid.addWidget(self.help_card, 4, 0)
            self.content_grid.setColumnStretch(0, 1)
            self.content_grid.setColumnStretch(1, 0)
        else:
            self.content_grid.addWidget(self.now_card, 0, 0)
            self.content_grid.addWidget(self.steps_card, 0, 1, 2, 1)
            self.content_grid.addWidget(self.host_card, 1, 0)
            self.content_grid.addWidget(self.device_card, 2, 0)
            self.content_grid.addWidget(self.help_card, 2, 1)
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

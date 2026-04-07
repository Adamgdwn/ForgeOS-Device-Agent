from __future__ import annotations

import json
import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.gui.control_app import ForgeControlApp


def _build_gui_harness(tmp_path: Path) -> tuple[ForgeControlApp, Path]:
    app = QApplication.instance() or QApplication([])
    session_dir = tmp_path / "devices" / "demo"
    (session_dir / "runtime" / "proposal").mkdir(parents=True)
    (session_dir / "runtime").mkdir(exist_ok=True)
    (session_dir / "runtime" / "proposal" / "proposal-manifest.json").write_text(
        json.dumps(
            {
                "selected_option_id": "lightweight_custom_android",
                "selected_option": {
                    "option_id": "lightweight_custom_android",
                    "included_features": [
                        {"id": "safe_defaults", "label": "Safe default configuration"},
                    ],
                    "optional_features": [
                        {"id": "extra_privacy", "label": "Extra privacy hardening"},
                    ],
                    "excluded_features": [
                        {"id": "full_google_bundle", "label": "Full Google bundle", "reason": "Excluded"},
                    ],
                },
                "options": [
                    {
                        "option_id": "lightweight_custom_android",
                        "label": "Lightweight custom Android",
                        "included_features": [
                            {"id": "safe_defaults", "label": "Safe default configuration"},
                        ],
                        "optional_features": [
                            {"id": "extra_privacy", "label": "Extra privacy hardening"},
                        ],
                        "excluded_features": [
                            {"id": "full_google_bundle", "label": "Full Google bundle", "reason": "Excluded"},
                        ],
                    }
                ],
            },
            indent=2,
        )
    )
    (session_dir / "runtime" / "operator-review.json").write_text(
        json.dumps(
            {
                "selected_option_id": "lightweight_custom_android",
                "fit_confirmed": False,
                "restore_confirmed": False,
                "limitations_accepted": False,
                "accepted_feature_ids": ["safe_defaults"],
                "rejected_feature_ids": ["extra_privacy"],
                "notes": "",
            },
            indent=2,
        )
    )

    gui = ForgeControlApp.__new__(ForgeControlApp)
    gui.qt_app = app
    gui.logger = logging.getLogger("test-gui-review")
    gui.current_session_dir = session_dir
    gui.review_form_dirty = False
    gui.review_form_syncing = False
    gui.review_form_session = None
    gui.proposal_choice_combo = QComboBox()
    gui.proposal_choice_combo.addItem("Lightweight custom Android", "lightweight_custom_android")
    gui.review_fit_check = QCheckBox()
    gui.review_restore_check = QCheckBox()
    gui.review_limitations_check = QCheckBox()
    gui.review_notes = QTextEdit()
    gui.review_status = QLabel()
    gui.review_text = QTextEdit()
    gui.review_feature_status = QLabel()
    gui.save_review_button = QPushButton()
    gui.review_feature_list = QWidget()
    gui.review_feature_layout = QVBoxLayout(gui.review_feature_list)
    gui.review_feature_checks = {}
    gui.refresh_ui = lambda _reason="": None
    gui._bind_review_form_signals()
    return gui, session_dir


def test_review_selection_survives_refresh_until_saved(tmp_path: Path) -> None:
    gui, session_dir = _build_gui_harness(tmp_path)
    runtime_plan = {
        "recommended_use_case": "lightweight_custom_android",
        "verification_execution": {
            "status": "executed",
            "summary": "Verification ready for review.",
        },
    }

    gui._refresh_feature_selection(session_dir, runtime_plan)
    gui._refresh_review_panel(session_dir, runtime_plan)

    assert not gui.review_fit_check.isChecked()
    assert not gui.review_feature_checks["extra_privacy"].isChecked()

    gui.review_fit_check.setChecked(True)
    gui.review_restore_check.setChecked(True)
    gui.review_limitations_check.setChecked(True)
    gui.review_feature_checks["extra_privacy"].setChecked(True)
    gui.review_notes.setPlainText("Keep the stricter privacy defaults.")

    assert gui.review_form_dirty is True

    gui._refresh_feature_selection(session_dir, runtime_plan)
    gui._refresh_review_panel(session_dir, runtime_plan)

    assert gui.review_fit_check.isChecked()
    assert gui.review_restore_check.isChecked()
    assert gui.review_limitations_check.isChecked()
    assert gui.review_feature_checks["extra_privacy"].isChecked()
    assert gui.review_notes.toPlainText() == "Keep the stricter privacy defaults."

    gui.save_operator_review()
    saved_review = json.loads((session_dir / "runtime" / "operator-review.json").read_text())

    assert saved_review["fit_confirmed"] is True
    assert saved_review["restore_confirmed"] is True
    assert saved_review["limitations_accepted"] is True
    assert "extra_privacy" in saved_review["accepted_feature_ids"]
    assert saved_review["notes"] == "Keep the stricter privacy defaults."
    assert gui.review_form_dirty is False


def test_saved_review_selection_survives_proposal_refresh(tmp_path: Path) -> None:
    gui, session_dir = _build_gui_harness(tmp_path)
    (session_dir / "runtime" / "proposal" / "proposal-manifest.json").write_text(
        json.dumps(
            {
                "recommended_use_case": "family_safe_android",
                "recommended_path": "research_only_path",
                "proposal_summary": "Saved operator choice should stay visible.",
                "selected_option_id": "lightweight_custom_android",
                "selected_option": {
                    "option_id": "lightweight_custom_android",
                    "label": "Lightweight custom Android",
                    "rationale": "Saved operator choice",
                    "included_features": [],
                    "optional_features": [],
                    "excluded_features": [],
                },
                "options": [
                    {
                        "option_id": "family_safe_android",
                        "label": "Family-safe Android",
                        "fit_score": 0.94,
                        "rationale": "Current recommendation",
                        "included_features": [],
                        "optional_features": [],
                        "excluded_features": [],
                    },
                    {
                        "option_id": "lightweight_custom_android",
                        "label": "Lightweight custom Android",
                        "fit_score": 0.89,
                        "rationale": "Saved operator choice",
                        "included_features": [],
                        "optional_features": [],
                        "excluded_features": [],
                    },
                ],
            },
            indent=2,
        )
    )
    (session_dir / "runtime" / "operator-review.json").write_text(
        json.dumps(
            {
                "selected_option_id": "lightweight_custom_android",
                "fit_confirmed": True,
                "restore_confirmed": True,
                "limitations_accepted": True,
                "accepted_feature_ids": [],
                "rejected_feature_ids": [],
                "notes": "Stick with the lighter build.",
            },
            indent=2,
        )
    )
    gui.proposal_status = QLabel()
    gui.proposal_os_label = QLabel()
    gui.proposal_notes = QTextEdit()
    gui.preview_folder_button = QPushButton()
    gui.preview_report_button = QPushButton()

    gui.proposal_choice_combo.clear()
    gui.proposal_choice_combo.addItem("Family-safe Android", "family_safe_android")
    gui.proposal_choice_combo.setCurrentIndex(0)

    runtime_plan = {
        "phase": "recommendation",
        "recommended_use_case": "family_safe_android",
        "recommended_path": "research_only_path",
        "preview_execution": {
            "status": "deferred",
            "mode": "mock",
            "summary": "Preview not ready yet.",
        },
        "recommendation_options": [
            {"option_id": "family_safe_android", "label": "Family-safe Android", "fit_score": 0.94, "rationale": "Current recommendation"},
            {"option_id": "lightweight_custom_android", "label": "Lightweight custom Android", "fit_score": 0.89, "rationale": "Saved operator choice"},
        ],
    }

    gui._refresh_proposal_panel(session_dir, runtime_plan)

    assert gui.proposal_choice_combo.currentData() == "lightweight_custom_android"

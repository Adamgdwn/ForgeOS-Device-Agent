from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path

from app.core.models import ForgePaths
from app.core.policy import PolicyEngine
from app.core.reporting import ReportWriter


WORKSPACE_FILE = "forgeos.code-workspace"


MASTER_SEEDS: dict[str, dict] = {
    "policies/default_policy.json": {
        "policy_version": "1.0",
        "default_dry_run": True,
        "require_restore_path": True,
        "allow_live_destructive_actions": False,
        "require_explicit_wipe_phrase": True,
        "allow_bootloader_relock": False,
        "open_vscode_on_launch": False,
        "open_vscode_on_session_create": True,
        "enable_codex_handoff": True,
        "priority_order": [
            "restore_path",
            "security",
            "connectivity",
            "core_operability",
            "functionality_expansion",
        ],
        "host_requirements": {
            "platforms": ["linux"],
            "preferred_desktop": "Pop!_OS",
            "tools": ["adb", "fastboot"],
        },
    },
    "manifests/sources.json": {
        "sources": [
            {
                "name": "aosp",
                "status": "reference",
                "notes": "Attach real manifests per supported device family.",
            }
        ]
    },
    "manifests/connection_adapters.json": {
        "adapters": [
            "adb",
            "fastboot",
            "fastbootd",
            "recovery",
            "mtp-bridge",
            "samsung-download",
            "codex-generated"
        ]
    },
    "reports/report_template.json": {
        "report_type": "template",
        "status": "draft",
        "summary": "Base report template",
        "details": {},
    },
    "strategies/default_strategies.json": {
        "strategies": [
            {
                "id": "research_only",
                "description": "Gather data only when restore or support path is not proven.",
            },
            {
                "id": "transport_recovery",
                "description": "Reach a manageable transport before OS selection.",
            },
            {
                "id": "hardened_stock",
                "description": "Prefer a stock-derived hardened path for stable, simple usage.",
            },
            {
                "id": "aftermarket_rom",
                "description": "Prefer an aftermarket path for developer-oriented usage.",
            },
            {
                "id": "privacy_hardened_aftermarket",
                "description": "Prefer a privacy-focused aftermarket path where support allows it.",
            },
            {
                "id": "hardened_existing_os",
                "description": "Prefer a maintainable hardening path when a clean-sheet build is risky.",
            }
        ]
    },
    "templates/codex_task_template.json": {
        "description": "Codex session brief is generated dynamically per device session."
    },
    "testplans/default_validation_plan.json": {
        "checks": [
            "usb_connectivity",
            "adb_reachability",
            "wifi_basic",
            "bluetooth_basic",
            "storage_health",
            "charging_state",
        ]
    },
}

KNOWLEDGE_SEEDS: dict[str, dict] = {
    "support_matrix.json": {
        "generated_at": None,
        "families": {},
    },
    "session_outcomes.json": {
        "outcomes": {},
    },
}

PROMOTION_SEEDS: dict[str, dict] = {
    "promotion_rules.json": {
        "min_observations_for_candidate": 3,
        "min_confidence_for_candidate": 0.75,
        "require_restore_path_ratio": 0.5,
        "require_non_research_strategy": True,
        "auto_apply_master_changes": False,
    },
    "candidates.json": {
        "generated_at": None,
        "rules": {},
        "candidates": [],
    },
}


def ensure_workspace_file(root: Path) -> Path:
    workspace_path = root / WORKSPACE_FILE
    if workspace_path.exists():
        return workspace_path
    workspace = {
        "folders": [
            {"path": "."},
            {"path": "master"},
            {"path": "devices"},
        ],
        "settings": {
            "python.defaultInterpreterPath": "python3",
        },
    }
    workspace_path.write_text(json.dumps(workspace, indent=2))
    return workspace_path


def seed_master_framework(root: Path) -> None:
    master_dir = root / "master"
    for relative_path, payload in MASTER_SEEDS.items():
        file_path = master_dir / relative_path
        if file_path.exists():
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, indent=2))
    for extra_dir in ["templates", "signing"]:
        (master_dir / extra_dir).mkdir(parents=True, exist_ok=True)


def seed_runtime_learning_framework(root: Path) -> None:
    for base_dir, seeds in [
        (root / "knowledge", KNOWLEDGE_SEEDS),
        (root / "promotion", PROMOTION_SEEDS),
    ]:
        base_dir.mkdir(parents=True, exist_ok=True)
        for relative_path, payload in seeds.items():
            file_path = base_dir / relative_path
            if file_path.exists():
                continue
            file_path.write_text(json.dumps(payload, indent=2))


def build_paths(root: Path) -> ForgePaths:
    return ForgePaths(
        root=root,
        app=root / "app",
        devices=root / "devices",
        knowledge=root / "knowledge",
        logs=root / "logs",
        master=root / "master",
        output=root / "output",
        promotion=root / "promotion",
        launcher=root / "launcher",
    )


def run_bootstrap(root: Path) -> dict[str, object]:
    paths = build_paths(root)
    for path in [
        paths.devices,
        paths.knowledge,
        paths.logs,
        paths.master,
        paths.output,
        paths.promotion,
        root / "tests",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    seed_master_framework(root)
    seed_runtime_learning_framework(root)
    workspace_path = ensure_workspace_file(root)

    policy = PolicyEngine(paths.master / "policies" / "default_policy.json").load()

    details = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "desktop_session": os.environ.get("XDG_CURRENT_DESKTOP"),
        "code_available": shutil.which("code") is not None,
        "adb_available": shutil.which("adb") is not None,
        "fastboot_available": shutil.which("fastboot") is not None,
        "udev_present": Path("/dev").exists(),
        "usb_access_likely": os.access("/dev", os.R_OK),
        "workspace_file": str(workspace_path),
        "policy_file": str(paths.master / "policies" / "default_policy.json"),
        "knowledge_dir": str(paths.knowledge),
        "promotion_dir": str(paths.promotion),
        "default_dry_run": policy.default_dry_run,
    }

    report_writer = ReportWriter(paths.output)
    report_path = report_writer.write_bootstrap(
        status="ok",
        summary="Bootstrap completed with environment discovery.",
        details=details,
    )

    details["bootstrap_report"] = str(report_path)
    return details

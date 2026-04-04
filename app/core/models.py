from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Transport(str, Enum):
    USB_ADB = "usb-adb"
    USB_FASTBOOT = "usb-fastboot"
    USB_FASTBOOTD = "usb-fastbootd"
    USB_RECOVERY = "usb-recovery"
    UNKNOWN = "unknown"


class SessionStateName(str, Enum):
    IDLE = "IDLE"
    DISCOVER = "DISCOVER"
    ASSESS = "ASSESS"
    BACKUP_PLAN = "BACKUP_PLAN"
    UNLOCK_PREP = "UNLOCK_PREP"
    UNLOCK = "UNLOCK"
    BASELINE_CAPTURE = "BASELINE_CAPTURE"
    PATH_SELECT = "PATH_SELECT"
    BUILD_GENERIC = "BUILD_GENERIC"
    BUILD_DEVICE = "BUILD_DEVICE"
    SIGN_IMAGES = "SIGN_IMAGES"
    FLASH_PREP = "FLASH_PREP"
    FLASH = "FLASH"
    BOOTSTRAP_DEVICE = "BOOTSTRAP_DEVICE"
    BRINGUP = "BRINGUP"
    HARDEN = "HARDEN"
    VALIDATE = "VALIDATE"
    PROMOTE = "PROMOTE"
    RESTORE = "RESTORE"
    BLOCKED = "BLOCKED"


class FailureSeverity(str, Enum):
    INFO = "info"
    TRANSIENT = "transient"
    RECOVERABLE = "recoverable"
    FATAL = "fatal"


class SupportStatus(str, Enum):
    ACTIONABLE = "actionable"
    RESEARCH_ONLY = "research_only"
    BLOCKED = "blocked"
    EXPERIMENTAL = "experimental"


@dataclass
class TransitionRecord:
    from_state: SessionStateName
    to_state: SessionStateName
    reason: str
    timestamp: str = field(default_factory=utc_now)


@dataclass
class DeviceFingerprint:
    manufacturer: str | None = None
    model: str | None = None
    serial: str | None = None
    transport: Transport = Transport.UNKNOWN
    short_fingerprint: str = ""
    stable_key: str = ""


@dataclass
class DeviceProfile:
    session_id: str
    canonical_name: str
    device_codename: str
    fingerprint: str
    manufacturer: str | None = None
    model: str | None = None
    serial: str | None = None
    android_version: str | None = None
    transport: Transport = Transport.UNKNOWN
    bootloader_locked: bool | None = None
    verified_boot_state: str | None = None
    slot_info: dict[str, Any] | None = None
    battery: dict[str, Any] | None = None
    raw_probe_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionState:
    session_id: str
    state: SessionStateName = SessionStateName.IDLE
    history: list[TransitionRecord] = field(default_factory=list)
    priority_order: list[str] = field(
        default_factory=lambda: [
            "safety_reversibility",
            "security",
            "connectivity",
            "core_operability",
            "functionality_expansion",
        ]
    )
    destructive_actions_approved: bool = False
    selected_strategy: str | None = None
    support_status: SupportStatus = SupportStatus.RESEARCH_ONLY
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    notes: list[str] = field(default_factory=list)


@dataclass
class PolicyModel:
    policy_version: str = "1.0"
    default_dry_run: bool = True
    require_restore_path: bool = True
    allow_bootloader_relock: bool = False
    open_vscode_on_launch: bool = True
    open_vscode_on_session_create: bool = True
    priority_order: list[str] = field(
        default_factory=lambda: [
            "restore_path",
            "security",
            "connectivity",
            "core_operability",
            "functionality_expansion",
        ]
    )
    host_requirements: dict[str, Any] = field(
        default_factory=lambda: {
            "platforms": ["linux"],
            "preferred_desktop": "Pop!_OS",
            "tools": ["adb", "fastboot"],
        }
    )


@dataclass
class BootstrapReport:
    status: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    report_type: str = "bootstrap"
    generated_at: str = field(default_factory=utc_now)


@dataclass
class ForgePaths:
    root: Path
    app: Path
    devices: Path
    logs: Path
    master: Path
    output: Path
    launcher: Path


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _serialize(val) for key, val in asdict(value).items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    return value


def to_dict(instance: Any) -> dict[str, Any]:
    return _serialize(instance)


def to_json(instance: Any) -> str:
    return json.dumps(to_dict(instance), indent=2)


def session_state_from_dict(data: dict[str, Any]) -> SessionState:
    history = [
        TransitionRecord(
            from_state=SessionStateName(item["from_state"]),
            to_state=SessionStateName(item["to_state"]),
            reason=item["reason"],
            timestamp=item["timestamp"],
        )
        for item in data.get("history", [])
    ]
    return SessionState(
        session_id=data["session_id"],
        state=SessionStateName(data["state"]),
        history=history,
        priority_order=data.get("priority_order", []),
        destructive_actions_approved=data.get("destructive_actions_approved", False),
        selected_strategy=data.get("selected_strategy"),
        support_status=SupportStatus(data.get("support_status", SupportStatus.RESEARCH_ONLY.value)),
        created_at=data.get("created_at", utc_now()),
        updated_at=data.get("updated_at", utc_now()),
        notes=data.get("notes", []),
    )


def device_profile_from_dict(data: dict[str, Any]) -> DeviceProfile:
    return DeviceProfile(
        session_id=data["session_id"],
        canonical_name=data["canonical_name"],
        device_codename=data["device_codename"],
        fingerprint=data["fingerprint"],
        manufacturer=data.get("manufacturer"),
        model=data.get("model"),
        serial=data.get("serial"),
        android_version=data.get("android_version"),
        transport=Transport(data.get("transport", Transport.UNKNOWN.value)),
        bootloader_locked=data.get("bootloader_locked"),
        verified_boot_state=data.get("verified_boot_state"),
        slot_info=data.get("slot_info"),
        battery=data.get("battery"),
        raw_probe_data=data.get("raw_probe_data", {}),
    )


def policy_from_dict(data: dict[str, Any]) -> PolicyModel:
    init_values = {}
    for field_info in fields(PolicyModel):
        if field_info.name in data:
            init_values[field_info.name] = data[field_info.name]
    return PolicyModel(**init_values)

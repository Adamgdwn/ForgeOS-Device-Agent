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
    USB_MTP = "usb-mtp"
    UNKNOWN = "unknown"


class SessionStateName(str, Enum):
    IDLE = "IDLE"
    DEVICE_ATTACHED = "DEVICE_ATTACHED"
    INTAKE = "INTAKE"
    ACCESS_ENABLEMENT = "ACCESS_ENABLEMENT"
    DISCOVER = "DISCOVER"
    DEEP_SCAN = "DEEP_SCAN"
    ASSESS = "ASSESS"
    PROFILE_SYNTHESIS = "PROFILE_SYNTHESIS"
    MATCH_MASTER = "MATCH_MASTER"
    RECOMMEND = "RECOMMEND"
    BACKUP_PLAN = "BACKUP_PLAN"
    BACKUP_READY = "BACKUP_READY"
    UNLOCK_PREP = "UNLOCK_PREP"
    UNLOCK = "UNLOCK"
    BASELINE_CAPTURE = "BASELINE_CAPTURE"
    PATH_SELECT = "PATH_SELECT"
    BLOCKER_CLASSIFY = "BLOCKER_CLASSIFY"
    REMEDIATION_DECIDE = "REMEDIATION_DECIDE"
    TASK_CREATE = "TASK_CREATE"
    CODEGEN_TASK = "CODEGEN_TASK"
    CODEGEN_WRITE = "CODEGEN_WRITE"
    PATCH_APPLY = "PATCH_APPLY"
    EXECUTE_STEP = "EXECUTE_STEP"
    EXECUTE_ARTIFACT = "EXECUTE_ARTIFACT"
    INSPECT_RESULT = "INSPECT_RESULT"
    CONNECTIVITY_VALIDATE = "CONNECTIVITY_VALIDATE"
    SECURITY_VALIDATE = "SECURITY_VALIDATE"
    BUILD_GENERIC = "BUILD_GENERIC"
    BUILD_DEVICE = "BUILD_DEVICE"
    PREVIEW_BUILD = "PREVIEW_BUILD"
    PREVIEW_REVIEW = "PREVIEW_REVIEW"
    INTERACTIVE_VERIFY = "INTERACTIVE_VERIFY"
    SIGN_IMAGES = "SIGN_IMAGES"
    FLASH_PREP = "FLASH_PREP"
    INSTALL_APPROVAL = "INSTALL_APPROVAL"
    FLASH = "FLASH"
    BOOTSTRAP_DEVICE = "BOOTSTRAP_DEVICE"
    BRINGUP = "BRINGUP"
    HARDEN = "HARDEN"
    VALIDATE = "VALIDATE"
    POST_INSTALL_VERIFY = "POST_INSTALL_VERIFY"
    COMPLETE = "COMPLETE"
    ITERATE = "ITERATE"
    QUESTION_GATE = "QUESTION_GATE"
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


class BlockerType(str, Enum):
    TRANSPORT = "transport_blocker"
    TRUST = "trust_blocker"
    SOURCE = "source_blocker"
    BUILD = "build_blocker"
    FLASH = "flash_blocker"
    BOOT = "boot_blocker"
    SUBSYSTEM = "subsystem_blocker"
    VALIDATION = "validation_blocker"
    POLICY = "policy_blocker"
    PHYSICAL = "physical_action_blocker"
    NONE = "none"


class UserPersona(str, Enum):
    DAILY = "daily_user"
    SENIOR = "senior"
    DEVELOPER = "developer"
    CHILD = "child"
    PRIVACY = "privacy_focused"


class TechnicalComfort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriorityFocus(str, Enum):
    SECURITY = "security"
    SIMPLICITY = "simplicity"
    PERFORMANCE = "performance"
    BATTERY = "battery"
    PRIVACY = "privacy"
    COMPATIBILITY = "compatibility"


class GoogleServicesPreference(str, Enum):
    KEEP = "keep_google"
    REDUCE = "reduce_google"
    REMOVE = "remove_google"


class AutonomyLimit(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGENTIC = "agentic"


class RiskTolerance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RestoreExpectation(str, Enum):
    MUST_BE_ONE_CLICK = "must_be_one_click"
    GUIDED_IS_OK = "guided_is_ok"
    RESEARCH_OK = "research_ok"


class UseCaseCategory(str, Enum):
    ACCESSIBILITY = "accessibility_focused_phone"
    KID_SAFE = "kid_safe_communication_device"
    MEDIA = "media_device"
    OFFLINE_UTILITY = "offline_utility_tool"
    HOME_CONTROL = "home_control_panel"
    LIGHTWEIGHT_ANDROID = "lightweight_custom_android"
    EXPERIMENTAL = "experimental_hybrid_path"
    KIOSK = "special_purpose_terminal"


class RuntimePhase(str, Enum):
    INTAKE = "intake"
    ACCESS = "guided_access_enablement"
    DISCOVERY = "deep_scan"
    RECOMMENDATION = "recommendation"
    BACKUP = "backup_restore"
    PREVIEW = "build_preview"
    VERIFICATION = "interactive_verification"
    INSTALL = "wipe_install"
    POST_INSTALL = "post_install_verification"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class WorkerRole(str, Enum):
    FRONTIER_ARCHITECT = "frontier_architect_worker"
    LOCAL_GENERAL = "local_general_worker"
    LOCAL_EDITOR = "local_editor_worker"
    POLICY_GUARD = "policy_guard"


class WorkerTier(str, Enum):
    FRONTIER = "frontier"
    LOCAL = "local"
    DETERMINISTIC = "deterministic"


class TaskRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


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
    current_blocker_type: str | None = None
    blocker_confidence: float = 0.0
    remediation_iteration: int = 0
    iterate_count: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    notes: list[str] = field(default_factory=list)


@dataclass
class PolicyModel:
    policy_version: str = "1.0"
    default_dry_run: bool = True
    require_restore_path: bool = True
    allow_live_destructive_actions: bool = False
    require_explicit_wipe_phrase: bool = True
    allow_bootloader_relock: bool = False
    open_vscode_on_launch: bool = False
    open_vscode_on_session_create: bool = False
    enable_codex_handoff: bool = True
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
class UserProfile:
    session_id: str
    persona: UserPersona = UserPersona.DAILY
    technical_comfort: TechnicalComfort = TechnicalComfort.LOW
    primary_priority: PriorityFocus = PriorityFocus.SECURITY
    google_services_preference: GoogleServicesPreference = GoogleServicesPreference.KEEP
    autonomy_limit: AutonomyLimit = AutonomyLimit.CONSERVATIVE
    risk_tolerance: RiskTolerance = RiskTolerance.LOW
    restore_expectation: RestoreExpectation = RestoreExpectation.MUST_BE_ONE_CLICK
    target_use_case: UseCaseCategory = UseCaseCategory.LIGHTWEIGHT_ANDROID
    notes: str = ""
    updated_at: str = field(default_factory=utc_now)


@dataclass
class OSGoals:
    session_id: str
    top_goal: PriorityFocus = PriorityFocus.SECURITY
    secondary_goal: PriorityFocus = PriorityFocus.SIMPLICITY
    requires_reliable_updates: bool = True
    prefers_long_battery_life: bool = True
    prefers_lockdown_defaults: bool = True
    updated_at: str = field(default_factory=utc_now)


@dataclass
class DestructiveApproval:
    session_id: str
    approved: bool = False
    approval_scope: str = "none"
    confirmation_phrase: str = ""
    approved_by: str = "local_operator"
    consequences_acknowledged: bool = False
    restore_path_confirmed: bool = False
    notes: str = ""
    approved_at: str | None = None
    updated_at: str = field(default_factory=utc_now)


@dataclass
class FlashPlan:
    session_id: str
    build_path: str
    dry_run: bool = True
    requires_unlock: bool = False
    requires_wipe: bool = True
    restore_path_available: bool = False
    artifacts_ready: bool = False
    install_mode: str = "unavailable"
    artifact_manifest_path: str = ""
    artifact_bundle_path: str = ""
    transport: str = Transport.UNKNOWN.value
    step_count: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)
    artifact_hints: list[str] = field(default_factory=list)
    status: str = "planned"
    summary: str = ""
    generated_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class WorkerRouteDecision:
    task_type: str
    selected_worker: WorkerRole
    selected_tier: WorkerTier
    rationale: str
    adapter_name: str
    fallback_worker: WorkerRole | None = None
    escalation_triggers: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now)


@dataclass
class RecommendationOption:
    option_id: str
    label: str
    fit_score: float
    rationale: str
    constraints: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class ApprovalGate:
    action: str
    allowed: bool
    requires_explicit_approval: bool
    reason: str
    missing_requirements: list[str] = field(default_factory=list)
    consequences: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now)


@dataclass
class RetryTelemetry:
    attempts: int = 0
    retry_budget: int = 0
    repeated_failure: bool = False
    exhausted: bool = False
    last_error: str = ""
    durations_ms: list[int] = field(default_factory=list)


@dataclass
class WorkerExecution:
    worker: str
    adapter_name: str
    task_type: str
    status: str
    summary: str
    command: list[str] = field(default_factory=list)
    transcript_path: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    confidence: float = 0.0
    escalation_triggers: list[str] = field(default_factory=list)
    telemetry: RetryTelemetry = field(default_factory=RetryTelemetry)
    structured_output: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=utc_now)


@dataclass
class PreviewExecution:
    status: str
    summary: str
    mode: str
    generated_files: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    capability_matrix: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=utc_now)


@dataclass
class VerificationExecution:
    status: str
    summary: str
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    interactive_checks: list[dict[str, Any]] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now)


@dataclass
class AuditEntry:
    category: str
    message: str
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)


@dataclass
class RuntimeSessionPlan:
    session_id: str
    phase: RuntimePhase
    mission: str
    operator_summary: str
    recommended_use_case: str
    recommended_path: str
    worker_routes: list[WorkerRouteDecision] = field(default_factory=list)
    worker_executions: list[WorkerExecution] = field(default_factory=list)
    recommendation_options: list[RecommendationOption] = field(default_factory=list)
    approval_gates: list[ApprovalGate] = field(default_factory=list)
    preview_execution: PreviewExecution | None = None
    verification_execution: VerificationExecution | None = None
    evidence: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    hard_stops: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=utc_now)


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
    knowledge: Path
    logs: Path
    master: Path
    output: Path
    promotion: Path
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
        current_blocker_type=data.get("current_blocker_type"),
        blocker_confidence=float(data.get("blocker_confidence", 0.0)),
        remediation_iteration=int(data.get("remediation_iteration", 0)),
        iterate_count=int(data.get("iterate_count", 0)),
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


def user_profile_from_dict(data: dict[str, Any]) -> UserProfile:
    return UserProfile(
        session_id=data["session_id"],
        persona=UserPersona(data.get("persona", UserPersona.DAILY.value)),
        technical_comfort=TechnicalComfort(
            data.get("technical_comfort", TechnicalComfort.LOW.value)
        ),
        primary_priority=PriorityFocus(
            data.get("primary_priority", PriorityFocus.SECURITY.value)
        ),
        google_services_preference=GoogleServicesPreference(
            data.get(
                "google_services_preference",
                GoogleServicesPreference.KEEP.value,
            )
        ),
        autonomy_limit=AutonomyLimit(data.get("autonomy_limit", AutonomyLimit.CONSERVATIVE.value)),
        risk_tolerance=RiskTolerance(data.get("risk_tolerance", RiskTolerance.LOW.value)),
        restore_expectation=RestoreExpectation(
            data.get("restore_expectation", RestoreExpectation.MUST_BE_ONE_CLICK.value)
        ),
        target_use_case=UseCaseCategory(
            data.get("target_use_case", UseCaseCategory.LIGHTWEIGHT_ANDROID.value)
        ),
        notes=data.get("notes", ""),
        updated_at=data.get("updated_at", utc_now()),
    )


def os_goals_from_dict(data: dict[str, Any]) -> OSGoals:
    return OSGoals(
        session_id=data["session_id"],
        top_goal=PriorityFocus(data.get("top_goal", PriorityFocus.SECURITY.value)),
        secondary_goal=PriorityFocus(
            data.get("secondary_goal", PriorityFocus.SIMPLICITY.value)
        ),
        requires_reliable_updates=data.get("requires_reliable_updates", True),
        prefers_long_battery_life=data.get("prefers_long_battery_life", True),
        prefers_lockdown_defaults=data.get("prefers_lockdown_defaults", True),
        updated_at=data.get("updated_at", utc_now()),
    )


def destructive_approval_from_dict(data: dict[str, Any]) -> DestructiveApproval:
    return DestructiveApproval(
        session_id=data["session_id"],
        approved=data.get("approved", False),
        approval_scope=data.get("approval_scope", "none"),
        confirmation_phrase=data.get("confirmation_phrase", ""),
        approved_by=data.get("approved_by", "local_operator"),
        consequences_acknowledged=data.get("consequences_acknowledged", False),
        restore_path_confirmed=data.get("restore_path_confirmed", False),
        notes=data.get("notes", ""),
        approved_at=data.get("approved_at"),
        updated_at=data.get("updated_at", utc_now()),
    )


def flash_plan_from_dict(data: dict[str, Any]) -> FlashPlan:
    return FlashPlan(
        session_id=data["session_id"],
        build_path=data.get("build_path", "unknown"),
        dry_run=data.get("dry_run", True),
        requires_unlock=data.get("requires_unlock", False),
        requires_wipe=data.get("requires_wipe", True),
        restore_path_available=data.get("restore_path_available", False),
        artifacts_ready=data.get("artifacts_ready", False),
        install_mode=data.get("install_mode", "unavailable"),
        artifact_manifest_path=data.get("artifact_manifest_path", ""),
        artifact_bundle_path=data.get("artifact_bundle_path", ""),
        transport=data.get("transport", Transport.UNKNOWN.value),
        step_count=data.get("step_count", len(data.get("steps", []))),
        steps=data.get("steps", []),
        artifact_hints=data.get("artifact_hints", []),
        status=data.get("status", "planned"),
        summary=data.get("summary", ""),
        generated_at=data.get("generated_at", utc_now()),
        updated_at=data.get("updated_at", utc_now()),
    )

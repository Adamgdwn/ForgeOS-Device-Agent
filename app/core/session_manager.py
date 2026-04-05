from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.core.models import (
    DestructiveApproval,
    DeviceProfile,
    FlashPlan,
    OSGoals,
    SessionState,
    SessionStateName,
    SupportStatus,
    TransitionRecord,
    Transport,
    device_profile_from_dict,
    destructive_approval_from_dict,
    flash_plan_from_dict,
    os_goals_from_dict,
    session_state_from_dict,
    to_json,
    utc_now,
    UserProfile,
    user_profile_from_dict,
)
from app.core.naming import build_fingerprint, canonical_session_name, generate_codename
from app.core.state_machine import is_transition_allowed


class SessionManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.devices_dir = root / "devices"
        self.master_dir = root / "master"

    def create_or_resume(self, probe_data: dict[str, Any]) -> Path:
        fingerprint = build_fingerprint(
            manufacturer=probe_data.get("manufacturer"),
            model=probe_data.get("model"),
            serial=probe_data.get("serial"),
            transport=probe_data.get("transport", Transport.UNKNOWN),
        )
        session_name = canonical_session_name(fingerprint)
        session_dir = self.devices_dir / session_name
        if not session_dir.exists():
            session_dir = self._find_upgrade_candidate(probe_data) or session_dir
        if session_dir.exists():
            profile = self.load_device_profile(session_dir)
            for key in [
                "manufacturer",
                "model",
                "serial",
                "android_version",
                "bootloader_locked",
                "verified_boot_state",
                "slot_info",
                "battery",
            ]:
                value = probe_data.get(key)
                if value is not None and value != "" and value != {}:
                    setattr(profile, key, value)
            transport = probe_data.get("transport")
            if transport:
                profile.transport = transport
            device_codename = probe_data.get("device_codename")
            if device_codename:
                profile.device_codename = device_codename
            profile.raw_probe_data |= probe_data
            self.write_device_profile(session_dir, profile)
            return session_dir

        session_dir.mkdir(parents=True, exist_ok=True)
        self._seed_session_from_master(session_dir)

        profile = DeviceProfile(
            session_id=session_name,
            canonical_name=session_name,
            device_codename=probe_data.get("device_codename") or generate_codename(fingerprint),
            fingerprint=fingerprint.stable_key,
            manufacturer=probe_data.get("manufacturer"),
            model=probe_data.get("model"),
            serial=probe_data.get("serial"),
            android_version=probe_data.get("android_version"),
            transport=probe_data.get("transport"),
            bootloader_locked=probe_data.get("bootloader_locked"),
            verified_boot_state=probe_data.get("verified_boot_state"),
            slot_info=probe_data.get("slot_info"),
            battery=probe_data.get("battery"),
            raw_probe_data=probe_data,
        )
        state = SessionState(
            session_id=session_name,
            state=SessionStateName.DEVICE_ATTACHED,
            support_status=SupportStatus.RESEARCH_ONLY,
            history=[
                TransitionRecord(
                    from_state=SessionStateName.IDLE,
                    to_state=SessionStateName.DEVICE_ATTACHED,
                    reason="Device detected",
                ),
            ],
        )
        self.write_device_profile(session_dir, profile)
        self.write_session_state(session_dir, state)
        self.write_user_profile(session_dir, UserProfile(session_id=session_name))
        self.write_os_goals(session_dir, OSGoals(session_id=session_name))
        self.write_destructive_approval(
            session_dir,
            DestructiveApproval(session_id=session_name),
        )
        return session_dir

    def _find_upgrade_candidate(self, probe_data: dict[str, Any]) -> Path | None:
        manufacturer = str(probe_data.get("manufacturer") or "").strip().lower()
        model = str(probe_data.get("model") or "").strip().lower()
        device_codename = str(probe_data.get("device_codename") or "").strip().lower()
        if not manufacturer and not model:
            return None
        for profile_path in sorted(self.devices_dir.glob("*/device-profile.json")):
            profile_data = json.loads(profile_path.read_text())
            existing_manufacturer = str(profile_data.get("manufacturer") or "").strip().lower()
            existing_model = str(profile_data.get("model") or "").strip().lower()
            existing_codename = str(profile_data.get("device_codename") or "").strip().lower()
            existing_serial = str(profile_data.get("serial") or "")
            same_identity = (
                (manufacturer and model and existing_manufacturer == manufacturer and existing_model == model)
                or (device_codename and existing_codename == device_codename)
            )
            coarse_serial = existing_serial.startswith("usb-")
            if same_identity and coarse_serial:
                return profile_path.parent
        return None

    def write_device_profile(self, session_dir: Path, profile: DeviceProfile) -> Path:
        path = session_dir / "device-profile.json"
        path.write_text(to_json(profile))
        return path

    def write_session_state(self, session_dir: Path, state: SessionState) -> Path:
        state.updated_at = utc_now()
        path = session_dir / "session-state.json"
        path.write_text(to_json(state))
        return path

    def load_session_state(self, session_dir: Path) -> SessionState:
        return session_state_from_dict(json.loads((session_dir / "session-state.json").read_text()))

    def load_device_profile(self, session_dir: Path) -> DeviceProfile:
        return device_profile_from_dict(json.loads((session_dir / "device-profile.json").read_text()))

    def write_user_profile(self, session_dir: Path, profile: UserProfile) -> Path:
        profile.updated_at = utc_now()
        path = session_dir / "user-profile.json"
        path.write_text(to_json(profile))
        return path

    def load_user_profile(self, session_dir: Path) -> UserProfile:
        path = session_dir / "user-profile.json"
        if not path.exists():
            session_id = session_dir.name
            profile = UserProfile(session_id=session_id)
            self.write_user_profile(session_dir, profile)
            return profile
        return user_profile_from_dict(json.loads(path.read_text()))

    def write_os_goals(self, session_dir: Path, goals: OSGoals) -> Path:
        goals.updated_at = utc_now()
        path = session_dir / "os-goals.json"
        path.write_text(to_json(goals))
        return path

    def load_os_goals(self, session_dir: Path) -> OSGoals:
        path = session_dir / "os-goals.json"
        if not path.exists():
            session_id = session_dir.name
            goals = OSGoals(session_id=session_id)
            self.write_os_goals(session_dir, goals)
            return goals
        return os_goals_from_dict(json.loads(path.read_text()))

    def write_destructive_approval(self, session_dir: Path, approval: DestructiveApproval) -> Path:
        approval.updated_at = utc_now()
        path = session_dir / "destructive-approval.json"
        path.write_text(to_json(approval))
        return path

    def load_destructive_approval(self, session_dir: Path) -> DestructiveApproval:
        path = session_dir / "destructive-approval.json"
        if not path.exists():
            approval = DestructiveApproval(session_id=session_dir.name)
            self.write_destructive_approval(session_dir, approval)
            return approval
        return destructive_approval_from_dict(json.loads(path.read_text()))

    def write_flash_plan(self, session_dir: Path, flash_plan: FlashPlan) -> Path:
        flash_plan.updated_at = utc_now()
        path = session_dir / "execution" / "flash-plan.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_json(flash_plan))
        return path

    def load_flash_plan(self, session_dir: Path) -> FlashPlan | None:
        path = session_dir / "execution" / "flash-plan.json"
        if not path.exists():
            return None
        return flash_plan_from_dict(json.loads(path.read_text()))

    def write_runtime_artifact(self, session_dir: Path, relative_path: str, payload: dict[str, Any]) -> Path:
        path = session_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        return path

    def transition(self, session_dir: Path, target: SessionStateName, reason: str) -> SessionState:
        state = self.load_session_state(session_dir)
        if not is_transition_allowed(state.state, target):
            raise ValueError(f"Illegal transition {state.state} -> {target}")
        state.history.append(
            TransitionRecord(from_state=state.state, to_state=target, reason=reason)
        )
        state.state = target
        return_state = self.write_session_state(session_dir, state)
        return state

    def annotate(self, session_dir: Path, note: str) -> SessionState:
        state = self.load_session_state(session_dir)
        state.notes.append(note)
        self.write_session_state(session_dir, state)
        return state

    def _seed_session_from_master(self, session_dir: Path) -> None:
        for directory in [
            "artifacts",
            "logs",
            "reports",
            "raw",
            "plans",
            "runtime",
            "codex",
            "connection",
            "codegen",
            "patches",
            "execution",
            "backup",
            "restore",
        ]:
            (session_dir / directory).mkdir(parents=True, exist_ok=True)
        strategies_src = self.master_dir / "strategies"
        plans_dest = session_dir / "plans" / "master-strategies"
        if strategies_src.exists() and not plans_dest.exists():
            shutil.copytree(strategies_src, plans_dest)

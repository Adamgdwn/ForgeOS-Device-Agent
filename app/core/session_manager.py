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


def _parse_battery_dump(dump: str) -> dict[str, Any]:
    """Extract key fields from `adb shell dumpsys battery` output."""
    result: dict[str, Any] = {}
    for line in dump.splitlines():
        line = line.strip()
        for key, field in [
            ("level:", "level"),
            ("status:", "status"),
            ("health:", "health"),
            ("temperature:", "temperature"),
            ("voltage:", "voltage"),
            ("AC powered:", "ac_powered"),
            ("USB powered:", "usb_powered"),
        ]:
            if line.startswith(key):
                raw = line[len(key):].strip()
                try:
                    result[field] = int(raw)
                except ValueError:
                    result[field] = raw.lower() in {"true", "yes", "1"}
    return result


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
            # Promote hardware_snapshot fields into top-level profile slots so
            # the assessor and blocker engine can use them without digging into
            # raw_probe_data.
            self._promote_hardware_snapshot(profile, probe_data)
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
        self._promote_hardware_snapshot(profile, probe_data)
        self.write_device_profile(session_dir, profile)
        self.write_session_state(session_dir, state)
        self.write_user_profile(session_dir, UserProfile(session_id=session_name))
        self.write_os_goals(session_dir, OSGoals(session_id=session_name))
        self.write_destructive_approval(
            session_dir,
            DestructiveApproval(session_id=session_name),
        )
        return session_dir

    @staticmethod
    def _promote_hardware_snapshot(profile: DeviceProfile, probe_data: dict[str, Any]) -> None:
        """Copy fields from hardware_snapshot into top-level DeviceProfile slots.

        The ADB watcher populates `hardware_snapshot` inside raw_probe_data but
        the profile's `bootloader_locked`, `verified_boot_state`, `battery`, and
        `slot_info` fields are left null because those keys are not present at the
        top level of the probe event.  This method fills those gaps so downstream
        tools see a fully populated profile without having to navigate raw_probe_data.
        """
        snapshot: dict[str, Any] = probe_data.get("hardware_snapshot") or {}
        if not snapshot:
            return

        # Bootloader lock state: prefer verified_boot_state (green=locked, orange=unlocked),
        # then fall back to warranty_bit (0=never unlocked=locked, 1=was unlocked),
        # then flash.locked (1=locked, 0=unlocked). Samsung often leaves vbs empty.
        if profile.bootloader_locked is None:
            vbs = str(snapshot.get("verified_boot_state") or "").strip().lower()
            if vbs == "green":
                profile.bootloader_locked = True
            elif vbs in {"orange", "yellow", "red"}:
                profile.bootloader_locked = False
            else:
                # vbs empty — try warranty_bit
                warranty = str(snapshot.get("warranty_bit") or "").strip()
                flash_locked = str(snapshot.get("flash_locked") or "").strip()
                if warranty == "0":
                    profile.bootloader_locked = True   # never unlocked
                elif warranty == "1":
                    profile.bootloader_locked = False  # was unlocked at some point
                elif flash_locked == "1":
                    profile.bootloader_locked = True
                elif flash_locked == "0":
                    profile.bootloader_locked = False

        # verified_boot_state string
        if not profile.verified_boot_state:
            vbs = str(snapshot.get("verified_boot_state") or "").strip()
            if vbs:
                profile.verified_boot_state = vbs

        # Slot info (A/B devices expose ro.boot.slot_suffix)
        if not profile.slot_info:
            slot_suffix = str(snapshot.get("boot_slot") or "").strip()
            if slot_suffix:
                profile.slot_info = {"active_slot": slot_suffix, "a_b_device": True}

        # Battery: parse the dumpsys battery dump into a concise dict
        if not profile.battery:
            battery_dump = str(snapshot.get("battery_dump") or "")
            if battery_dump:
                profile.battery = _parse_battery_dump(battery_dump)

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
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(to_json(state))
        tmp_path.replace(path)
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

    def find_waiting_session(self, serial: str) -> Path | None:
        if not serial:
            return None
        for state_path in sorted(self.devices_dir.glob("*/session-state.json")):
            try:
                state_data = json.loads(state_path.read_text())
                if state_data.get("state") != SessionStateName.QUESTION_GATE.value:
                    continue
                profile_data = json.loads((state_path.parent / "device-profile.json").read_text())
            except Exception:
                continue
            if str(profile_data.get("serial") or "") == serial:
                return state_path.parent
        return None

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

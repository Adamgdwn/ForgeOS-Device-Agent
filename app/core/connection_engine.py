from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.models import DeviceProfile, SessionState, SupportStatus, utc_now


@dataclass
class ConnectionAdapter:
    adapter_id: str
    label: str
    transport_match: set[str]
    vendor_match: set[str]
    priority: int
    destructive: bool = False
    notes: str = ""
    next_steps: list[str] | None = None

    def score(self, profile: DeviceProfile) -> int:
        score = self.priority
        transport = profile.transport.value
        if transport in self.transport_match:
            score += 80
        if profile.manufacturer and profile.manufacturer.lower() in {item.lower() for item in self.vendor_match}:
            score += 25
        return score


class ConnectionEngine:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.adapters = [
            ConnectionAdapter(
                adapter_id="adb",
                label="Android Debug Bridge",
                transport_match={"usb-adb"},
                vendor_match=set(),
                priority=100,
                notes="Preferred non-destructive path when USB debugging is authorized.",
                next_steps=["Query device properties via adb shell.", "Collect slot and partition clues."],
            ),
            ConnectionAdapter(
                adapter_id="fastboot",
                label="Fastboot",
                transport_match={"usb-fastboot", "usb-fastbootd"},
                vendor_match=set(),
                priority=90,
                notes="Low-level transport for unlock, flash planning, and partition inspection where supported.",
                next_steps=["Query fastboot variables.", "Check unlock and slot support."],
            ),
            ConnectionAdapter(
                adapter_id="recovery",
                label="Recovery",
                transport_match={"usb-recovery"},
                vendor_match=set(),
                priority=70,
                notes="Fallback recovery-mode path for backup or rescue workflows.",
                next_steps=["Identify recovery environment.", "Assess sideload and restore possibilities."],
            ),
            ConnectionAdapter(
                adapter_id="mtp-bridge",
                label="MTP / USB User-Space Bridge",
                transport_match={"usb-mtp"},
                vendor_match=set(),
                priority=40,
                notes="USB-only visibility. Useful for identification and user-guided transition toward adb or OEM tools.",
                next_steps=[
                    "Guide user to enable USB debugging.",
                    "Attempt adb server/reconnect once phone trust is granted.",
                ],
            ),
            ConnectionAdapter(
                adapter_id="samsung-download",
                label="Samsung Download / Heimdall",
                transport_match={"usb-mtp", "unknown"},
                vendor_match={"Samsung"},
                priority=45,
                notes="Samsung-specific escalation path when adb is unavailable and the device can enter download mode.",
                next_steps=[
                    "Determine whether device can reach download mode.",
                    "Prepare Heimdall/Odin-compatible research path.",
                ],
            ),
            ConnectionAdapter(
                adapter_id="codex-generated",
                label="Codex-Generated Adapter",
                transport_match={"usb-mtp", "unknown", "usb-adb", "usb-fastboot", "usb-fastbootd", "usb-recovery"},
                vendor_match=set(),
                priority=30,
                notes="Fallback path where Codex should generate a device-specific probe or connection helper.",
                next_steps=[
                    "Inspect raw probe data and USB IDs.",
                    "Generate missing adapter scripts in the device session.",
                ],
            ),
        ]

    def build_plan(
        self,
        profile: DeviceProfile,
        session_state: SessionState,
        assessment: dict[str, Any],
        engagement: dict[str, Any],
    ) -> dict[str, Any]:
        ranked = sorted(
            [
                {
                    "adapter_id": adapter.adapter_id,
                    "label": adapter.label,
                    "score": adapter.score(profile),
                    "destructive": adapter.destructive,
                    "notes": adapter.notes,
                    "next_steps": adapter.next_steps or [],
                }
                for adapter in self.adapters
            ],
            key=lambda item: item["score"],
            reverse=True,
        )
        recommended = ranked[0] if ranked else None
        engagement_status = engagement.get("engagement_status")
        transport = profile.transport.value
        managed_transport_active = transport in {"usb-adb", "usb-fastboot", "usb-fastbootd", "usb-recovery"}
        requires_codex_generation = (
            transport in {"usb-mtp", "unknown"}
            or session_state.support_status in {SupportStatus.RESEARCH_ONLY, SupportStatus.EXPERIMENTAL}
        )
        if managed_transport_active and engagement_status in {"adb_connected", "fastboot_connected", "recovery_connected"}:
            requires_codex_generation = False
        elif recommended and recommended.get("adapter_id") in {"adb", "fastboot", "recovery"} and managed_transport_active:
            requires_codex_generation = False
        plan = {
            "generated_at": utc_now(),
            "device_session": profile.session_id,
            "transport": transport,
            "support_status": session_state.support_status.value,
            "assessment_summary": assessment.get("summary"),
            "engagement_status": engagement_status,
            "recommended_adapter": recommended,
            "adapter_candidates": ranked,
            "requires_codex_generation": requires_codex_generation,
        }
        return plan

    def write_plan(self, session_dir: Path, plan: dict[str, Any]) -> Path:
        path = session_dir / "plans" / "connection-plan.json"
        path.write_text(json.dumps(plan, indent=2))
        return path

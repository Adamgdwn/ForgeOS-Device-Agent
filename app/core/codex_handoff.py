from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import DeviceProfile, OSGoals, SessionState, UserProfile, utc_now


class CodexHandoffEngine:
    def __init__(self, root: Path) -> None:
        self.root = root

    def prepare(
        self,
        session_dir: Path,
        profile: DeviceProfile,
        session_state: SessionState,
        user_profile: UserProfile,
        os_goals: OSGoals,
        assessment: dict[str, Any],
        engagement: dict[str, Any],
        connection_plan: dict[str, Any],
        blocker: dict[str, Any] | None = None,
        build_plan: dict[str, Any] | None = None,
        knowledge_match: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        handoff_dir = session_dir / "codex"
        handoff_dir.mkdir(parents=True, exist_ok=True)

        handoff_json = {
            "generated_at": utc_now(),
            "session_id": profile.session_id,
            "device": {
                "manufacturer": profile.manufacturer,
                "model": profile.model,
                "serial": profile.serial,
                "transport": profile.transport.value,
                "codename": profile.device_codename,
                "fingerprint": profile.fingerprint,
            },
            "session_state": session_state.state.value,
            "support_status": session_state.support_status.value,
            "selected_strategy": session_state.selected_strategy,
            "user_profile": {
                "persona": user_profile.persona.value,
                "technical_comfort": user_profile.technical_comfort.value,
                "primary_priority": user_profile.primary_priority.value,
                "google_services_preference": user_profile.google_services_preference.value,
                "notes": user_profile.notes,
            },
            "os_goals": {
                "top_goal": os_goals.top_goal.value,
                "secondary_goal": os_goals.secondary_goal.value,
                "requires_reliable_updates": os_goals.requires_reliable_updates,
                "prefers_long_battery_life": os_goals.prefers_long_battery_life,
                "prefers_lockdown_defaults": os_goals.prefers_lockdown_defaults,
            },
            "assessment": assessment,
            "engagement": engagement,
            "connection_plan": connection_plan,
            "blocker": blocker or {},
            "build_plan": build_plan or {},
            "knowledge_match": knowledge_match or {},
            "objective": (
                "Use Codex to build or refine the device-specific connection, probe, and custom OS strategy "
                "for this exact phone while preserving the reusable master framework."
            ),
        }
        handoff_json_path = handoff_dir / "codex-handoff.json"
        handoff_json_path.write_text(json.dumps(handoff_json, indent=2))

        task_text = self._task_markdown(
            profile,
            session_state,
            user_profile,
            os_goals,
            assessment,
            engagement,
            connection_plan,
            blocker or {},
            build_plan or {},
            knowledge_match or {},
        )
        task_path = handoff_dir / "CODEX_TASK.md"
        task_path.write_text(task_text)

        workspace_path = handoff_dir / "device-session.code-workspace"
        workspace_path.write_text(
            json.dumps(
                {
                    "folders": [
                        {"path": str(self.root)},
                        {"path": str(session_dir)},
                    ],
                    "settings": {
                        "python.defaultInterpreterPath": str(self.root / ".venv" / "bin" / "python"),
                    },
                },
                indent=2,
            )
        )

        return {
            "handoff_json": str(handoff_json_path),
            "task_markdown": str(task_path),
            "workspace_file": str(workspace_path),
        }

    def _task_markdown(
        self,
        profile: DeviceProfile,
        session_state: SessionState,
        user_profile: UserProfile,
        os_goals: OSGoals,
        assessment: dict[str, Any],
        engagement: dict[str, Any],
        connection_plan: dict[str, Any],
        blocker: dict[str, Any],
        build_plan: dict[str, Any],
        knowledge_match: dict[str, Any],
    ) -> str:
        recommended = connection_plan.get("recommended_adapter") or {}
        adapter_candidates = connection_plan.get("adapter_candidates") or []
        candidate_lines = "\n".join(
            f"- `{item['adapter_id']}` ({item['label']}), score {item['score']}: {item['notes']}"
            for item in adapter_candidates[:5]
        )
        next_steps = engagement.get("next_steps") or []
        next_step_lines = "\n".join(f"- {step}" for step in next_steps) or "- None recorded"
        return f"""# Codex Task Brief

## Mission

Use this device session to build whatever connection, probe, and custom-OS preparation logic is required for this exact phone while preserving the reusable `master/` framework.

## Device Summary

- Manufacturer: {profile.manufacturer or "unknown"}
- Model: {profile.model or "unknown"}
- Serial: {profile.serial or "unknown"}
- Transport: {profile.transport.value}
- Device codename: {profile.device_codename}
- Session state: {session_state.state.value}
- Support status: {session_state.support_status.value}
- Selected strategy: {session_state.selected_strategy or "not selected"}

## User Profile

- Persona: {user_profile.persona.value}
- Technical comfort: {user_profile.technical_comfort.value}
- Primary priority: {user_profile.primary_priority.value}
- Google services preference: {user_profile.google_services_preference.value}
- Notes: {user_profile.notes or "none"}

## OS Goals

- Top goal: {os_goals.top_goal.value}
- Secondary goal: {os_goals.secondary_goal.value}
- Reliable updates required: {os_goals.requires_reliable_updates}
- Long battery life preferred: {os_goals.prefers_long_battery_life}
- Lockdown defaults preferred: {os_goals.prefers_lockdown_defaults}

## Current Assessment

{assessment.get("summary", "No assessment summary available")}

## Current Autonomous Engagement

{engagement.get("summary", "No engagement summary available")}

Current user-side blocker or next action:
{next_step_lines}

## Connection Engine Recommendation

- Recommended adapter: `{recommended.get("adapter_id", "unknown")}` ({recommended.get("label", "unknown")})
- Requires Codex generation: {connection_plan.get("requires_codex_generation")}

Candidate adapters:
{candidate_lines}

## Current Blocker

- Type: {blocker.get("blocker_type", "unknown")}
- Machine solvable: {blocker.get("machine_solvable")}
- Summary: {blocker.get("summary", "No blocker summary available")}

## Build Path Resolution

- Recommended OS path: {build_plan.get("os_path", "unknown")}
- Why: {build_plan.get("reason", "No build-path rationale available")}

## Prior Knowledge Match

{knowledge_match.get("family_summary") or "No prior device-family knowledge was found."}

## Codex Objectives

1. Inspect the session reports, raw probe data, and connection plan.
2. Decide what new scripts, manifests, or adapters are needed for this exact device.
3. Build those assets inside this device session first, not in `master/`.
4. Promote reusable patterns into `master/` only if they are clearly generic and safe.
5. Prioritize transport, recovery, and non-destructive assessment before build novelty.

## Output Expectations

- Add or refine connection helpers under this session if needed.
- Improve probe coverage for this exact device.
- Write auditable notes and plans, not hidden state.
- Stop honestly if the hardware or phone policy blocks further autonomous control.
"""

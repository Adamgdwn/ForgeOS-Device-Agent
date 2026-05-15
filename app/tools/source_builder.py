from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool


class SourceBuilderTool(BaseTool):
    name = "source_builder"
    input_schema = {
        "session_dir": "string",
        "device": "object",
        "build_plan": "object",
        "policy": "object",
        "research": "object",
    }
    output_schema = {"status": "string", "strategy": "string", "details": "object"}

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        session_dir = Path(str(payload["session_dir"]))
        device = dict(payload.get("device", {}))
        build_plan = dict(payload.get("build_plan", {}))
        policy = dict(payload.get("policy", {}))
        research = dict(payload.get("research", {}))
        build_dir = session_dir / "runtime" / "build-from-source"
        output_dir = session_dir / "artifacts" / "os-source"
        build_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        strategy = self._select_strategy(device=device, build_plan=build_plan, research=research)
        plan = self._build_plan(
            session_dir=session_dir,
            output_dir=output_dir,
            device=device,
            build_plan=build_plan,
            strategy=strategy,
            research=research,
        )
        plan_path = build_dir / "source-build-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2))
        request_path = build_dir / "source-build-request.json"
        request_path.write_text(json.dumps(self._request_for_plan(plan), indent=2))
        script_path = build_dir / "build_source_artifacts.sh"
        script_path.write_text(self._script_for_plan(plan))
        script_path.chmod(0o755)

        allow_build = bool(policy.get("allow_long_source_builds", False))
        max_seconds = int(policy.get("max_source_build_seconds", 28800))
        attempt = {
            "status": "not_started",
            "reason": "Policy does not allow long local source builds.",
            "staged_files": self._built_outputs(output_dir),
        }
        if allow_build:
            attempt = self._execute_plan(
                session_dir=session_dir,
                script_path=script_path,
                output_dir=output_dir,
                device=device,
                timeout=max_seconds,
            )
        if attempt.get("staged_files"):
            status = "ready"
        elif allow_build and attempt.get("status") == "failed":
            status = "build_failed"
        elif allow_build:
            status = "build_pending"
        else:
            status = "build_plan_ready"
        return {
            "status": status,
            "strategy": strategy["id"],
            "details": {
                "plan_path": str(plan_path),
                "request_path": str(request_path),
                "script_path": str(script_path),
                "output_dir": str(output_dir),
                "plan": plan,
                "attempt": attempt,
                "staged_files": attempt.get("staged_files", []),
            },
        }

    def _select_strategy(
        self,
        *,
        device: dict[str, Any],
        build_plan: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        codename = str(device.get("device_codename") or "")
        if os.environ.get("FORGEOS_ANDROID_BUILD_COMMAND", "").strip():
            return {
                "id": "configured_local_build",
                "reason": "A local Android build command is configured for this host.",
            }
        if codename and research.get("lineageos_supported") is not False:
            return {
                "id": "lineageos_source_build",
                "reason": "Device codename is known and LineageOS-style source build is the best general open build path.",
            }
        if build_plan.get("selected_option_id") in {"home_control_panel", "media_device", "accessibility_focused_phone"}:
            return {
                "id": "stock_hardening_bundle",
                "reason": "No complete ROM source path is known, so build a restorable stock-derived configuration bundle while source work continues.",
            }
        return {
            "id": "aosp_generic_source_build",
            "reason": "Fallback to a generic AOSP/GSI-style build plan when no device-specific ROM path is known.",
        }

    def _build_plan(
        self,
        *,
        session_dir: Path,
        output_dir: Path,
        device: dict[str, Any],
        build_plan: dict[str, Any],
        strategy: dict[str, Any],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        codename = str(device.get("device_codename") or "")
        model = str(device.get("model") or "")
        command = os.environ.get("FORGEOS_ANDROID_BUILD_COMMAND", "").strip()
        if not command and strategy["id"] == "lineageos_source_build":
            command = "bash runtime/build-from-source/build_lineageos_candidate.sh"
        elif not command and strategy["id"] == "aosp_generic_source_build":
            command = "bash runtime/build-from-source/build_aosp_candidate.sh"
        elif not command:
            command = "bash runtime/build-from-source/build_stock_hardening_bundle.sh"

        return {
            "status": "planned",
            "strategy": strategy,
            "device": {
                "manufacturer": device.get("manufacturer"),
                "model": model,
                "device_codename": codename,
                "android_version": device.get("android_version"),
            },
            "build_path": build_plan.get("os_path", "unknown"),
            "output_dir": str(output_dir),
            "command": command,
            "research": {
                "lineageos_supported": research.get("lineageos_supported"),
                "twrp_supported": research.get("twrp_supported"),
                "community_notes": research.get("community_notes", ""),
                "flash_procedure_hints": research.get("flash_procedure_hints", []),
            },
            "required_outputs": [
                "OTA or recovery ZIP larger than 10 MiB",
                "or fastboot image archive/image set larger than 10 MiB",
            ],
            "session_dir": str(session_dir),
        }

    def _request_for_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        device = dict(plan.get("device", {}))
        strategy = dict(plan.get("strategy", {}))
        return {
            "status": "build_required",
            "reason": strategy.get("reason", "No trusted ready-made package met the build threshold."),
            "manufacturer": device.get("manufacturer") or "",
            "model": device.get("model") or "",
            "device_codename": device.get("device_codename") or "",
            "recommended_builder": strategy.get("id", "unknown"),
            "required_outputs": plan.get("required_outputs", []),
            "commands": [
                f"Run `{plan.get('command', '')}` from the session folder.",
                "Let the Android source sync/build complete on the local machine.",
                f"Place generated OTA ZIPs or fastboot image sets under {plan.get('output_dir', '')}.",
                "ForgeOS will re-stage those outputs automatically on the next runtime pass.",
            ],
        }

    def _script_for_plan(self, plan: dict[str, Any]) -> str:
        strategy_id = str(plan["strategy"]["id"])
        command = str(plan["command"])
        codename = str(plan["device"].get("device_codename") or "")
        output_dir = str(plan["output_dir"])
        helper_scripts = self._helper_scripts(strategy_id=strategy_id, codename=codename, output_dir=output_dir)
        return "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "",
                f"export FORGEOS_DEVICE_CODENAME={json.dumps(codename)}",
                f"export FORGEOS_SOURCE_OUTPUT_DIR={json.dumps(output_dir)}",
                "mkdir -p \"${FORGEOS_SOURCE_OUTPUT_DIR}\"",
                "",
                helper_scripts,
                "",
                command,
            ]
        ) + "\n"

    def _helper_scripts(self, *, strategy_id: str, codename: str, output_dir: str) -> str:
        if strategy_id == "configured_local_build":
            return "# Running operator-configured local Android build command."
        if strategy_id == "lineageos_source_build":
            return self._lineage_helper(codename=codename, output_dir=output_dir)
        if strategy_id == "aosp_generic_source_build":
            return self._aosp_helper(output_dir=output_dir)
        return self._stock_bundle_helper(output_dir=output_dir)

    def _lineage_helper(self, *, codename: str, output_dir: str) -> str:
        return "\n".join(
            [
                "cat > runtime/build-from-source/build_lineageos_candidate.sh <<'EOS'",
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "if [[ -z \"${FORGEOS_DEVICE_CODENAME:-}\" ]]; then echo 'Missing device codename' >&2; exit 2; fi",
                "if ! command -v repo >/dev/null 2>&1; then echo 'Android repo tool is required' >&2; exit 3; fi",
                "WORK=${FORGEOS_ANDROID_BUILD_WORKDIR:-$PWD/runtime/build-from-source/lineage-work}",
                "mkdir -p \"$WORK\" \"$FORGEOS_SOURCE_OUTPUT_DIR\"",
                "cd \"$WORK\"",
                "if [[ ! -d .repo ]]; then repo init -u https://github.com/LineageOS/android.git -b ${FORGEOS_LINEAGE_BRANCH:-lineage-22.2}; fi",
                "repo sync -c --no-clone-bundle --optimized-fetch -j${FORGEOS_SYNC_JOBS:-4}",
                "source build/envsetup.sh",
                "breakfast \"${FORGEOS_DEVICE_CODENAME}\"",
                "mka bacon -j${FORGEOS_BUILD_JOBS:-$(nproc)}",
                "find out/target/product/${FORGEOS_DEVICE_CODENAME} -maxdepth 1 -type f \\( -name '*.zip' -o -name '*.img' -o -name '*.tar' \\) -size +10M -exec cp -v {} \"$FORGEOS_SOURCE_OUTPUT_DIR\" \\;",
                "EOS",
                "chmod +x runtime/build-from-source/build_lineageos_candidate.sh",
            ]
        )

    def _aosp_helper(self, *, output_dir: str) -> str:
        return "\n".join(
            [
                "cat > runtime/build-from-source/build_aosp_candidate.sh <<'EOS'",
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "if ! command -v repo >/dev/null 2>&1; then echo 'Android repo tool is required' >&2; exit 3; fi",
                "WORK=${FORGEOS_ANDROID_BUILD_WORKDIR:-$PWD/runtime/build-from-source/aosp-work}",
                "mkdir -p \"$WORK\" \"$FORGEOS_SOURCE_OUTPUT_DIR\"",
                "cd \"$WORK\"",
                "if [[ ! -d .repo ]]; then repo init -u https://android.googlesource.com/platform/manifest -b ${FORGEOS_AOSP_BRANCH:-android-15.0.0_r1}; fi",
                "repo sync -c --no-clone-bundle --optimized-fetch -j${FORGEOS_SYNC_JOBS:-4}",
                "source build/envsetup.sh",
                "lunch ${FORGEOS_AOSP_LUNCH:-aosp_arm64-eng}",
                "m -j${FORGEOS_BUILD_JOBS:-$(nproc)}",
                "find out/target/product -type f \\( -name '*.zip' -o -name '*.img' -o -name '*.tar' \\) -size +10M -exec cp -v {} \"$FORGEOS_SOURCE_OUTPUT_DIR\" \\;",
                "EOS",
                "chmod +x runtime/build-from-source/build_aosp_candidate.sh",
            ]
        )

    def _stock_bundle_helper(self, *, output_dir: str) -> str:
        return "\n".join(
            [
                "cat > runtime/build-from-source/build_stock_hardening_bundle.sh <<'EOS'",
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "mkdir -p \"$FORGEOS_SOURCE_OUTPUT_DIR\"",
                "tar -C \"$PWD\" -czf \"$FORGEOS_SOURCE_OUTPUT_DIR/stock-hardening-session-bundle.tar.gz\" user-profile.json os-goals.json runtime 2>/dev/null || true",
                "echo 'Generated a stock hardening bundle. A full ROM still requires vendor/device source or a trusted flashable package.'",
                "EOS",
                "chmod +x runtime/build-from-source/build_stock_hardening_bundle.sh",
            ]
        )

    def _execute_plan(
        self,
        *,
        session_dir: Path,
        script_path: Path,
        output_dir: Path,
        device: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        env = {
            **os.environ,
            "FORGEOS_SESSION_DIR": str(session_dir),
            "FORGEOS_SOURCE_OUTPUT_DIR": str(output_dir),
            "FORGEOS_DEVICE_CODENAME": str(device.get("device_codename") or ""),
            "FORGEOS_DEVICE_MODEL": str(device.get("model") or ""),
        }
        try:
            completed = subprocess.run(
                [str(script_path)],
                cwd=session_dir,
                capture_output=True,
                text=True,
                check=False,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            result = {
                "status": "failed",
                "returncode": -1,
                "stdout": str(exc.stdout or "")[-4000:],
                "stderr": "source build timed out",
                "staged_files": self._built_outputs(output_dir),
            }
            self._write_transcript(session_dir, result)
            return result
        staged_files = self._built_outputs(output_dir)
        result = {
            "status": "completed" if completed.returncode == 0 and staged_files else "failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "staged_files": staged_files,
            "tools": {
                "repo": bool(shutil.which("repo")),
                "java": bool(shutil.which("java")),
                "ccache": bool(shutil.which("ccache")),
            },
        }
        self._write_transcript(session_dir, result)
        return result

    def _write_transcript(self, session_dir: Path, result: dict[str, Any]) -> None:
        transcript_path = session_dir / "runtime" / "build-from-source" / "build-transcript.json"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        result["transcript_path"] = str(transcript_path)
        transcript_path.write_text(json.dumps(result, indent=2))

    def _built_outputs(self, output_dir: Path) -> list[str]:
        if not output_dir.exists():
            return []
        outputs: list[str] = []
        for path in sorted(output_dir.iterdir()):
            if not path.is_file():
                continue
            name = path.name.lower()
            if not any(name.endswith(suffix) for suffix in [".zip", ".img", ".tar", ".tar.gz", ".tgz"]):
                continue
            if path.stat().st_size <= 10 * 1024 * 1024:
                continue
            outputs.append(str(path))
        return outputs

from __future__ import annotations

import json
import shutil
import tarfile
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool


class ImageBuilderTool(BaseTool):
    name = "image_builder"
    input_schema = {"session_dir": "string", "build_plan": "object", "device": "object"}
    output_schema = {"artifacts": "array", "status": "string", "details": "object"}

    _FASTBOOT_ORDER = [
        "boot.img",
        "init_boot.img",
        "vendor_boot.img",
        "dtbo.img",
        "vbmeta.img",
        "vbmeta_system.img",
        "recovery.img",
        "system.img",
        "vendor.img",
        "product.img",
        "super.img",
    ]

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        session_dir = Path(str(payload["session_dir"]))
        build_plan = dict(payload.get("build_plan", {}))
        source_dir = session_dir / "artifacts" / "os-source"
        build_dir = session_dir / "runtime" / "build"
        staged_dir = build_dir / "staged"
        source_dir.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir(parents=True, exist_ok=True)
        staged_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = build_dir / "artifact-manifest.json"
        bundle_path = build_dir / "flashable-artifacts.tar.gz"
        readme_path = build_dir / "README.md"
        source_readme_path = source_dir / "README.md"
        if not source_readme_path.exists():
            source_readme_path.write_text(
                "\n".join(
                    [
                        "# Stage Install Source Artifacts Here",
                        "",
                        "Supported generic inputs:",
                        "- `update.zip`, `ota.zip`, or `payload.zip` for adb sideload",
                        "- fastboot images such as `boot.img`, `system.img`, `vendor.img`, `vbmeta.img`, `super.img`",
                        "",
                        "ForgeOS will stage these into `runtime/build/` and only enable install execution when a real artifact set is present.",
                    ]
                )
                + "\n"
            )

        sideload_zip = self._find_sideload_zip(source_dir)
        fastboot_images = self._find_fastboot_images(source_dir)

        status = "missing_source"
        install_mode = "unavailable"
        staged_files: list[Path] = []
        flash_steps: list[dict[str, str]] = []
        missing: list[str] = []

        if sideload_zip:
            copied = staged_dir / sideload_zip.name
            shutil.copy2(sideload_zip, copied)
            staged_files.append(copied)
            status = "ready"
            install_mode = "adb_sideload"
            flash_steps = [
                {
                    "name": "sideload_update",
                    "kind": "flash",
                    "command": f"adb sideload {copied.name}",
                    "description": "Apply the staged OTA or recovery package over adb sideload.",
                }
            ]
        elif fastboot_images:
            status = "ready"
            install_mode = "fastboot_images"
            for partition, source_path in fastboot_images:
                copied = staged_dir / source_path.name
                shutil.copy2(source_path, copied)
                staged_files.append(copied)
                flash_steps.append(
                    {
                        "name": f"flash_{partition}",
                        "kind": "flash",
                        "command": f"fastboot flash {partition} {copied.name}",
                        "description": f"Flash `{partition}` from `{copied.name}`.",
                    }
                )
        else:
            missing = [
                f"Stage an OTA-style package such as `update.zip` under {source_dir}",
                f"or stage fastboot images such as `boot.img`, `system.img`, or `vendor.img` under {source_dir}.",
            ]

        if status == "ready":
            with tarfile.open(bundle_path, "w:gz") as tar:
                for staged in staged_files:
                    tar.add(staged, arcname=staged.name)
        elif bundle_path.exists():
            bundle_path.unlink()

        manifest = {
            "status": status,
            "install_mode": install_mode,
            "source_dir": str(source_dir),
            "build_path": build_plan.get("os_path", "unknown"),
            "proposed_os_name": build_plan.get("proposed_os_name", "Unknown build profile"),
            "staged_files": [str(path) for path in staged_files],
            "bundle_path": str(bundle_path) if status == "ready" else "",
            "flash_steps": flash_steps,
            "missing_requirements": missing,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))
        readme_path.write_text(self._readme_text(manifest))

        artifacts = [str(manifest_path), str(readme_path), str(source_readme_path)]
        if status == "ready":
            artifacts.append(str(bundle_path))
            artifacts.extend(str(path) for path in staged_files)
        return {
            "status": status,
            "artifacts": artifacts,
            "details": manifest,
        }

    def _find_sideload_zip(self, source_dir: Path) -> Path | None:
        if not source_dir.exists():
            return None
        for name in ["update.zip", "ota.zip", "payload.zip"]:
            candidate = source_dir / name
            if candidate.exists():
                return candidate
        return None

    def _find_fastboot_images(self, source_dir: Path) -> list[tuple[str, Path]]:
        if not source_dir.exists():
            return []
        images: list[tuple[str, Path]] = []
        for filename in self._FASTBOOT_ORDER:
            candidate = source_dir / filename
            if candidate.exists():
                images.append((filename.removesuffix(".img"), candidate))
        return images

    def _readme_text(self, manifest: dict[str, Any]) -> str:
        lines = [
            "# ForgeOS Build Staging",
            "",
            f"Status: {manifest.get('status', 'unknown')}",
            f"Install mode: {manifest.get('install_mode', 'unknown')}",
            f"Proposed OS profile: {manifest.get('proposed_os_name', 'Unknown build profile')}",
            f"Source directory: {manifest.get('source_dir', 'unknown')}",
            "",
        ]
        if manifest.get("status") == "ready":
            lines.extend(
                [
                    "Staged files:",
                    *[f"- {Path(path).name}" for path in manifest.get("staged_files", [])],
                    "",
                    "Planned install commands:",
                    *[f"- {step.get('command', '')}" for step in manifest.get("flash_steps", [])],
                ]
            )
        else:
            lines.extend(
                [
                    "Missing requirements:",
                    *[f"- {item}" for item in manifest.get("missing_requirements", [])],
                ]
            )
        return "\n".join(lines) + "\n"

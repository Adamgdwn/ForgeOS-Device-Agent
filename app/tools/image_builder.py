from __future__ import annotations

import json
import shutil
import tarfile
import zipfile
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

    # Heimdall partition name → common image filename patterns
    _HEIMDALL_PARTITION_PATTERNS: dict[str, list[str]] = {
        "RECOVERY": ["recovery.img", "twrp*.img", "recovery*.img"],
        "BOOT":     ["boot.img"],
        "SYSTEM":   ["system.img"],
        "VENDOR":   ["vendor.img"],
        "USERDATA": ["userdata.img"],
        "CACHE":    ["cache.img"],
        "BL":       ["bl.img", "bootloader.img"],
        "CP":       ["cp.img", "modem.img"],
    }
    _MIN_IMAGE_BYTES = 1024 * 1024

    def __init__(self, root: Path) -> None:
        super().__init__(root)

    def run(self, payload: dict[str, object]) -> dict[str, object]:
        session_dir = Path(str(payload["session_dir"]))
        build_plan = dict(payload.get("build_plan", {}))
        source_dir = session_dir / "artifacts" / "os-source"
        build_dir = session_dir / "runtime" / "build"
        staged_dir = build_dir / "staged"
        extracted_dir = build_dir / "extracted"
        source_dir.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir(parents=True, exist_ok=True)
        staged_dir.mkdir(parents=True, exist_ok=True)
        extracted_dir.mkdir(parents=True, exist_ok=True)
        self._clear_staged_outputs(staged_dir)

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
                        "- Android OTA or recovery ZIP packages, including LineageOS-style named ZIPs",
                        "- fastboot images such as `boot.img`, `system.img`, `vendor.img`, `vbmeta.img`, `super.img`",
                        "- ZIP or tar archives containing fastboot images",
                        "",
                        "ForgeOS will stage these into `runtime/build/` and only enable install execution when a real artifact set is present.",
                    ]
                )
                + "\n"
            )

        sideload_zip = self._find_sideload_zip(source_dir)
        fastboot_images = self._find_fastboot_images(source_dir)
        device = dict(payload.get("device", {}))
        manufacturer = str(device.get("manufacturer") or "").strip().lower()
        prefer_heimdall = manufacturer == "samsung"
        heimdall_images = self._find_heimdall_images(source_dir) if prefer_heimdall else []
        source_artifact = str(sideload_zip) if sideload_zip else ""
        if not sideload_zip and not fastboot_images and not heimdall_images:
            extracted = self._extract_fastboot_archive(source_dir, extracted_dir)
            if extracted:
                fastboot_images = extracted
                source_artifact = str(extracted[0][1].parent)
            if not fastboot_images and prefer_heimdall:
                heimdall_images = self._extract_samsung_archive(source_dir, extracted_dir)

        status = "missing_source"
        install_mode = "unavailable"
        staged_files: list[Path] = []
        flash_steps: list[dict[str, str]] = []
        missing: list[str] = []

        if heimdall_images:
            status = "ready"
            install_mode = "heimdall_flash"
            partitions: dict[str, str] = {}
            for partition, source_path in heimdall_images:
                copied = staged_dir / source_path.name
                shutil.copy2(source_path, copied)
                staged_files.append(copied)
                partitions[partition] = copied.name
            flash_steps = [
                {
                    "name": "flash_samsung",
                    "kind": "flash",
                    "command": "heimdall flash " + " ".join(f"--{p} {f}" for p, f in partitions.items()),
                    "partitions": partitions,
                    "description": "Flash Samsung partitions via Heimdall in Download Mode.",
                }
            ]
        elif sideload_zip:
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
                f"Stage an Android OTA or recovery ZIP under {source_dir}",
                f"or stage real fastboot images such as `boot.img`, `system.img`, or `vendor.img` under {source_dir}.",
                "Tiny placeholders and simulated image files are ignored.",
                f"Fastboot image archives are also supported when they contain recognized `.img` partition files larger than {self._MIN_IMAGE_BYTES // 1024 // 1024} MiB.",
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
            "source_artifact": source_artifact,
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
            if candidate.exists() and self._is_android_sideload_zip(candidate):
                return candidate
        for candidate in sorted(source_dir.glob("*.zip")):
            if self._is_android_sideload_zip(candidate):
                return candidate
        return None

    def _is_android_sideload_zip(self, candidate: Path) -> bool:
        try:
            with zipfile.ZipFile(candidate) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return False
        return bool(
            "payload.bin" in names
            or "META-INF/com/google/android/update-binary" in names
            or "META-INF/com/android/metadata" in names
            or "META-INF/com/google/android/metadata" in names
        )

    def _find_heimdall_images(self, source_dir: Path) -> list[tuple[str, Path]]:
        """Find images that should be flashed via Heimdall (Samsung Download Mode)."""
        if not source_dir.exists():
            return []
        found: list[tuple[str, Path]] = []
        all_imgs = [path for path in source_dir.glob("*.img") if self._is_plausible_image(path)]
        for partition, patterns in self._HEIMDALL_PARTITION_PATTERNS.items():
            for pattern in patterns:
                for img in all_imgs:
                    import fnmatch
                    if fnmatch.fnmatch(img.name.lower(), pattern.lower()):
                        found.append((partition, img))
                        break
                if any(p == partition for p, _ in found):
                    break
        return found

    def _extract_samsung_archive(self, source_dir: Path, extracted_dir: Path) -> list[tuple[str, Path]]:
        """Extract Samsung tar.md5 firmware archives and return heimdall-ready image pairs."""
        samsung_archives = [
            *sorted(source_dir.glob("*.tar.md5")),
            *sorted(source_dir.glob("AP_*.tar")),
            *sorted(source_dir.glob("BL_*.tar")),
        ]
        if not samsung_archives:
            return []
        target_dir = extracted_dir / "samsung_extracted"
        target_dir.mkdir(parents=True, exist_ok=True)
        for archive_path in samsung_archives:
            try:
                open_path = archive_path
                if archive_path.suffix == ".md5":
                    open_path = archive_path.with_suffix("")
                    if not open_path.exists():
                        import shutil as _sh
                        _sh.copy2(archive_path, open_path)
                with tarfile.open(open_path) as tar:
                    for member in tar.getmembers():
                        fname = Path(member.name).name
                        if member.isfile() and (fname.endswith(".img") or fname.endswith(".img.lz4")):
                            tar.extract(member, target_dir)
            except Exception as exc:
                self.logger.warning("Samsung archive extraction failed for %s: %s", archive_path.name, exc)
        # Decompress any .lz4 files
        for lz4_file in target_dir.rglob("*.img.lz4"):
            out = lz4_file.with_suffix("")
            if not out.exists():
                try:
                    import subprocess as _sp
                    _sp.run(["lz4", "-d", str(lz4_file), str(out)], check=False, capture_output=True)
                except Exception:
                    pass
        return self._find_heimdall_images(target_dir)

    def _find_fastboot_images(self, source_dir: Path) -> list[tuple[str, Path]]:
        if not source_dir.exists():
            return []
        images: list[tuple[str, Path]] = []
        for filename in self._FASTBOOT_ORDER:
            candidate = source_dir / filename
            if candidate.exists() and self._is_plausible_image(candidate):
                images.append((filename.removesuffix(".img"), candidate))
        return images

    def _is_plausible_image(self, path: Path) -> bool:
        try:
            if path.stat().st_size < self._MIN_IMAGE_BYTES:
                return False
            sample = path.read_bytes()[:256]
        except OSError:
            return False
        lowered = sample.lower()
        if b"simulated firmware content" in lowered or b"placeholder" in lowered:
            return False
        return True

    def _clear_staged_outputs(self, staged_dir: Path) -> None:
        for path in staged_dir.iterdir():
            if path.is_file():
                path.unlink()

    def _extract_fastboot_archive(self, source_dir: Path, extracted_dir: Path) -> list[tuple[str, Path]]:
        archives = [
            *sorted(source_dir.glob("*.zip")),
            *sorted(source_dir.glob("*.tar")),
            *sorted(source_dir.glob("*.tar.gz")),
            *sorted(source_dir.glob("*.tgz")),
        ]
        for archive_path in archives:
            target_dir = extracted_dir / archive_path.name.replace(".", "_")
            target_dir.mkdir(parents=True, exist_ok=True)
            try:
                if archive_path.suffix == ".zip":
                    with zipfile.ZipFile(archive_path) as archive:
                        for member in archive.namelist():
                            filename = Path(member).name
                            if filename in self._FASTBOOT_ORDER:
                                archive.extract(member, target_dir)
                                extracted = target_dir / member
                                flat_target = target_dir / filename
                                if extracted.resolve() != flat_target.resolve():
                                    shutil.copy2(extracted, flat_target)
                elif tarfile.is_tarfile(archive_path):
                    with tarfile.open(archive_path) as archive:
                        for member in archive.getmembers():
                            filename = Path(member.name).name
                            if member.isfile() and filename in self._FASTBOOT_ORDER:
                                archive.extract(member, target_dir)
                                extracted = target_dir / member.name
                                flat_target = target_dir / filename
                                if extracted.resolve() != flat_target.resolve():
                                    shutil.copy2(extracted, flat_target)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Could not extract fastboot archive %s: %s", archive_path, exc)
                continue
            images = self._find_fastboot_images(target_dir)
            if images:
                return images
        return []

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

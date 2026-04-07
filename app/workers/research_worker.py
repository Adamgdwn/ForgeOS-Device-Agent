from __future__ import annotations

"""ResearchWorker — uses the local Ollama/Goose setup to research devices.

Research flow:
  1. Read the session backup file (device-metadata-backup.json) to extract the
     full getprop snapshot — this is the richest possible device description and
     is already on disk before research runs.
  2. Build a structured prompt from those facts.
  3. Ask the local Ollama model to reason about firmware sources, unlock procedure,
     known issues, and recommended approach from its training knowledge.
  4. If Goose is available, dispatch a follow-up web search prompt through Goose
     so it can fetch live community pages (XDA, LineageOS wiki, TWRP device list).
  5. Merge both results and write them to devices/<session>/research/<topic>.json.

No API key required. No external dependencies beyond what is already configured
for the local worker runtime (Ollama + optionally Goose).
"""

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from app.core.models import utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backup file parsing
# ---------------------------------------------------------------------------

def _parse_getprop(getprop_stdout: str) -> dict[str, str]:
    """Parse `adb shell getprop` output into a flat key→value dict."""
    props: dict[str, str] = {}
    for line in getprop_stdout.splitlines():
        m = re.match(r"\[(.+?)\]:\s*\[(.*)?\]", line)
        if m:
            props[m.group(1)] = m.group(2)
    return props


def _parse_packages(packages_stdout: str) -> list[str]:
    """Parse `pm list packages` output into a list of package names."""
    packages = []
    for line in packages_stdout.splitlines():
        if line.startswith("package:"):
            packages.append(line[len("package:"):].strip())
    return packages


def read_backup_facts(session_dir: Path) -> dict[str, Any]:
    """Read the session backup file and extract structured device facts.

    Returns a dict with: props (full getprop), key_props (the important subset),
    packages (installed app list), battery (state dict), raw_backup (full capture).
    """
    backup_path = session_dir / "backup" / "device-metadata-backup.json"
    if not backup_path.exists():
        return {"available": False, "reason": "backup file not found"}

    try:
        backup = json.loads(backup_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"backup parse error: {exc}"}

    captures = backup.get("captures", {})

    # Full getprop → flat dict
    getprop_raw = captures.get("getprop", {}).get("stdout", "")
    props = _parse_getprop(getprop_raw)

    # Key properties that drive research
    key_props = {
        "manufacturer": props.get("ro.product.manufacturer") or props.get("ro.product.brand", ""),
        "model": props.get("ro.product.model", ""),
        "device": props.get("ro.product.device", ""),
        "name": props.get("ro.product.name", ""),
        "board": props.get("ro.board.platform") or props.get("ro.hardware", ""),
        "android_version": props.get("ro.build.version.release", ""),
        "android_sdk": props.get("ro.build.version.sdk", ""),
        "build_fingerprint": props.get("ro.build.fingerprint", ""),
        "build_type": props.get("ro.build.type", ""),
        "cpu_abi": props.get("ro.product.cpu.abi", ""),
        "cpu_abi2": props.get("ro.product.cpu.abi2", ""),
        "slot_suffix": props.get("ro.boot.slot_suffix", ""),
        "dynamic_partitions": props.get("ro.boot.dynamic_partitions", ""),
        "ab_update": props.get("ro.build.ab_update", ""),
        "verified_boot": props.get("ro.boot.verifiedbootstate", ""),
        "bootloader": props.get("ro.bootloader", ""),
        "baseband": props.get("ro.baseband") or props.get("gsm.version.baseband", ""),
        "security_patch": props.get("ro.build.version.security_patch", ""),
        "treble": props.get("ro.treble.enabled", ""),
    }

    packages_raw = captures.get("packages", {}).get("stdout", "")
    packages = _parse_packages(packages_raw)

    battery_raw = captures.get("battery", {}).get("stdout", "")

    return {
        "available": True,
        "key_props": {k: v for k, v in key_props.items() if v},
        "props": props,
        "packages": packages,
        "battery_raw": battery_raw,
        "transport": backup.get("transport", "unknown"),
        "adb_metadata_available": backup.get("adb_metadata_available", False),
    }


# ---------------------------------------------------------------------------
# Local subprocess helpers
# ---------------------------------------------------------------------------

def _ollama_executable() -> str:
    return os.environ.get("FORGEOS_OLLAMA_EXECUTABLE", "ollama")


def _ollama_model() -> str:
    return os.environ.get("FORGEOS_OLLAMA_MODEL", "qwen3:8b")


def _goose_executable() -> str:
    return os.environ.get("FORGEOS_GOOSE_EXECUTABLE", "goose")


def _goose_provider() -> str:
    return os.environ.get("FORGEOS_GOOSE_PROVIDER", "ollama")


def _goose_model() -> str:
    return os.environ.get("FORGEOS_GOOSE_MODEL", "qwen3:8b")


def _ollama_available() -> bool:
    import shutil
    return shutil.which(_ollama_executable()) is not None


def _goose_available() -> bool:
    import shutil
    return shutil.which(_goose_executable()) is not None


def _run_ollama(prompt: str, timeout: int = 120) -> dict[str, Any]:
    """Call ollama and return stdout, stderr, returncode."""
    cmd = [_ollama_executable(), "run", _ollama_model(), prompt, "--format", "json", "--hidethinking"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
        return {"ok": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "ollama timed out"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "stdout": "", "stderr": str(exc)}


def _run_goose(prompt: str, cwd: Path, timeout: int = 180) -> dict[str, Any]:
    """Call goose and return stdout, stderr, returncode."""
    cmd = [
        _goose_executable(), "run",
        "--text", prompt,
        "--no-session", "--quiet",
        "--provider", _goose_provider(),
        "--model", _goose_model(),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=timeout, cwd=cwd
        )
        return {"ok": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "goose timed out"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "stdout": "", "stderr": str(exc)}


def _strip_ansi(text: str) -> str:
    """Strip ANSI terminal escape codes from Ollama streaming output."""
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07|\r", "", text)


def _try_parse_json_from_text(text: str) -> dict[str, Any] | None:
    """Try to extract the first JSON object from a (potentially ANSI-decorated) text response."""
    text = _strip_ansi(text)
    # First try parsing the whole thing
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except Exception:  # noqa: BLE001
        pass
    # Find the outermost { ... } block
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:  # noqa: BLE001
                    start = -1  # bad block, keep scanning
    return None


# ---------------------------------------------------------------------------
# ResearchWorker
# ---------------------------------------------------------------------------

class ResearchWorker:
    """Autonomous local research worker.

    Uses Ollama for knowledge-base reasoning and Goose for live web search.
    All inputs are derived from the session backup file — no manual configuration
    required after the device is connected and the backup runs.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.ollama_available = _ollama_available()
        self.goose_available = _goose_available()
        self.available = self.ollama_available or self.goose_available
        if not self.available:
            logger.warning(
                "ResearchWorker: neither ollama nor goose is available. "
                "Install one of them to enable autonomous device research."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def research_firmware(
        self,
        session_dir: Path,
        manufacturer: str,
        model: str,
        codename: str,
        android_version: str,
        transport: str,
    ) -> dict[str, Any]:
        """Find firmware sources and flash procedures for a device.

        Reads the session backup first to enrich the query with exact getprop facts.
        """
        backup = read_backup_facts(session_dir)
        kp = backup.get("key_props", {})

        # Prefer backup-derived values over caller-supplied values when richer
        manufacturer = kp.get("manufacturer") or manufacturer
        model = kp.get("model") or model
        codename = kp.get("device") or codename
        android_version = kp.get("android_version") or android_version
        board = kp.get("board", "")
        fingerprint = kp.get("build_fingerprint", "")
        ab_slots = kp.get("slot_suffix") in {"_a", "_b"} or kp.get("ab_update") == "true"

        device_summary = self._format_device_summary(kp, backup)

        ollama_prompt = f"""You are a mobile device firmware expert. Based on the following device profile,
identify the best available firmware and custom ROM options.

DEVICE PROFILE (from live getprop backup):
{device_summary}

Please provide a JSON response with these fields:
{{
  "firmware_sources": [
    {{"name": "...", "url_hint": "...", "notes": "..."}}
  ],
  "flash_procedure_hints": ["step 1", "step 2"],
  "lineageos_supported": true/false/null,
  "twrp_supported": true/false/null,
  "grapheneos_supported": true/false/null,
  "unlock_procedure": "brief description",
  "anti_rollback_risk": true/false,
  "community_notes": "any important warnings or tips",
  "confidence": 0.0-1.0
}}

Base your answer on your training knowledge of this device."""

        result = self._run_with_fallback(
            session_dir=session_dir,
            topic="firmware_sources",
            ollama_prompt=ollama_prompt,
            goose_prompt=(
                f"You are researching firmware options for {manufacturer} {model} "
                f"(codename: {codename}, board: {board}, Android {android_version}).\n\n"
                "Use shell commands to fetch these pages and extract relevant information:\n"
                f"  curl -sL 'https://wiki.lineageos.org/devices/{codename}' 2>/dev/null | head -200\n"
                f"  curl -sL 'https://twrp.me/search/?q={codename}' 2>/dev/null | grep -i '{codename}\\|download' | head -30\n"
                f"  curl -sL 'https://xdaforums.com/search/?\""
                f"q={codename}+firmware&o=date' 2>/dev/null | grep -i 'title\\|href' | head -30\n\n"
                "Then summarise what you found and return JSON with fields:\n"
                "firmware_sources (list of {name, url_hint, notes}), "
                "flash_procedure_hints (list of steps), "
                "lineageos_supported (true/false/null), "
                "twrp_supported (true/false/null), "
                "unlock_procedure (string), "
                "community_notes (string), "
                "confidence (0.0-1.0)"
            ),
            goose_cwd=session_dir,
            extract_fn=self._extract_firmware_result,
            fallback={
                "firmware_sources": [],
                "flash_procedure_hints": [],
                "lineageos_supported": None,
                "twrp_supported": None,
                "grapheneos_supported": None,
                "unlock_procedure": "",
                "anti_rollback_risk": None,
                "community_notes": "",
                "confidence": 0.0,
            },
        )
        result["device_summary"] = device_summary
        return result

    def research_device(
        self,
        session_dir: Path,
        manufacturer: str,
        model: str,
        codename: str,
        board: str,
        abi: str,
    ) -> dict[str, Any]:
        """Look up community knowledge about a device: quirks, unlock methods, ROM support."""
        backup = read_backup_facts(session_dir)
        kp = backup.get("key_props", {})

        manufacturer = kp.get("manufacturer") or manufacturer
        model = kp.get("model") or model
        codename = kp.get("device") or codename
        board = kp.get("board") or board
        abi = kp.get("cpu_abi") or abi

        device_summary = self._format_device_summary(kp, backup)

        ollama_prompt = f"""You are a mobile device expert. Analyze this device profile and provide technical guidance.

DEVICE PROFILE (from live getprop backup):
{device_summary}

Respond with JSON:
{{
  "device_facts": {{
    "partition_scheme": "A/B or single-slot",
    "treble_compliant": true/false/null,
    "dynamic_partitions": true/false/null,
    "oem_tool_required": "none or tool name (e.g. Heimdall, SP Flash Tool)"
  }},
  "unlock_procedure": "step-by-step summary",
  "known_issues": ["issue 1", "issue 2"],
  "recommended_approach": "one of: lineageos, grapheneos, stock_reflash, research_only",
  "confidence": 0.0-1.0
}}"""

        return self._run_with_fallback(
            session_dir=session_dir,
            topic="device_community",
            ollama_prompt=ollama_prompt,
            goose_prompt=(
                f"Research technical details for {manufacturer} {model} "
                f"(codename: {codename}, board: {board}, ABI: {abi}).\n\n"
                "Use shell commands:\n"
                f"  curl -sL 'https://wiki.lineageos.org/devices/{codename}' 2>/dev/null | head -150\n"
                f"  curl -sL 'https://twrp.me/search/?q={codename}' 2>/dev/null | head -80\n\n"
                "Return JSON with: device_facts (partition_scheme, treble_compliant, dynamic_partitions, "
                "oem_tool_required), unlock_procedure, known_issues (list), "
                "recommended_approach, confidence (0.0-1.0)"
            ),
            goose_cwd=session_dir,
            extract_fn=self._extract_device_result,
            fallback={
                "device_facts": {},
                "unlock_procedure": "",
                "known_issues": [],
                "recommended_approach": "research_only",
                "confidence": 0.0,
            },
        )

    def research_blocker(
        self,
        session_dir: Path,
        manufacturer: str,
        model: str,
        blocker_type: str,
        blocker_summary: str,
        transport: str,
    ) -> dict[str, Any]:
        """Search for solutions to a specific persistent blocker."""
        backup = read_backup_facts(session_dir)
        kp = backup.get("key_props", {})
        manufacturer = kp.get("manufacturer") or manufacturer
        model = kp.get("model") or model
        device_summary = self._format_device_summary(kp, backup)

        ollama_prompt = f"""You are a mobile device repair expert. Help solve this problem.

DEVICE PROFILE:
{device_summary}

PROBLEM: {blocker_summary}
BLOCKER TYPE: {blocker_type}
TRANSPORT: {transport}

Respond with JSON:
{{
  "solutions": ["solution 1", "solution 2"],
  "next_steps": ["step 1", "step 2"],
  "references": ["XDA thread title or URL hint"],
  "confidence": 0.0-1.0
}}"""

        return self._run_with_fallback(
            session_dir=session_dir,
            topic=f"blocker_{blocker_type}",
            ollama_prompt=ollama_prompt,
            goose_prompt=(
                f"I have a {manufacturer} {model} stuck on: {blocker_summary}\n"
                f"Transport: {transport}\n\n"
                "Use shell commands to search for solutions:\n"
                f"  curl -sL 'https://xdaforums.com/search/?q={manufacturer}+{model}+"
                f"{blocker_type.replace('_blocker','')}&o=date' 2>/dev/null | "
                "grep -i 'title\\|solution\\|fix' | head -30\n\n"
                "Return JSON with: solutions (list), next_steps (list), "
                "references (list of url/title), confidence (0.0-1.0)"
            ),
            goose_cwd=session_dir,
            extract_fn=self._extract_blocker_result,
            fallback={
                "solutions": [],
                "next_steps": [],
                "references": [],
                "confidence": 0.0,
            },
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _format_device_summary(kp: dict[str, str], backup: dict[str, Any]) -> str:
        """Format key props into a readable block for LLM prompts."""
        lines = []
        field_labels = [
            ("manufacturer", "Manufacturer"),
            ("model", "Model"),
            ("device", "Codename"),
            ("name", "Product name"),
            ("board", "Board/SoC"),
            ("android_version", "Android version"),
            ("android_sdk", "SDK level"),
            ("cpu_abi", "CPU ABI"),
            ("slot_suffix", "Slot suffix (A/B indicator)"),
            ("dynamic_partitions", "Dynamic partitions"),
            ("ab_update", "A/B update"),
            ("verified_boot", "Verified boot state"),
            ("security_patch", "Security patch"),
            ("treble", "Treble enabled"),
            ("build_fingerprint", "Build fingerprint"),
        ]
        for key, label in field_labels:
            val = kp.get(key, "")
            if val:
                lines.append(f"  {label}: {val}")
        pkg_count = len(backup.get("packages", []))
        if pkg_count:
            lines.append(f"  Installed packages: {pkg_count} apps captured")
        transport = backup.get("transport", "")
        if transport:
            lines.append(f"  Transport at backup time: {transport}")
        return "\n".join(lines) if lines else "  (no getprop data available)"

    def _run_with_fallback(
        self,
        session_dir: Path,
        topic: str,
        ollama_prompt: str,
        goose_prompt: str,
        goose_cwd: Path,
        extract_fn: Any,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        research_dir = session_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        result_path = research_dir / f"{topic}.json"

        if not self.available:
            result = {
                **fallback,
                "status": "workers_unavailable",
                "topic": topic,
                "generated_at": utc_now(),
                "note": "Install ollama or goose to enable autonomous device research.",
            }
            result_path.write_text(json.dumps(result, indent=2))
            return result

        raw_text = ""
        source = "none"

        # Try Ollama first (fast, local, no network needed for reasoning)
        if self.ollama_available:
            ollama_result = _run_ollama(ollama_prompt)
            if ollama_result["ok"] and ollama_result["stdout"]:
                raw_text = ollama_result["stdout"]
                source = "ollama"

        # If Ollama didn't produce usable output, try Goose (can browse the web)
        if not raw_text and self.goose_available:
            goose_result = _run_goose(goose_prompt, cwd=goose_cwd)
            if goose_result["ok"] and goose_result["stdout"]:
                raw_text = goose_result["stdout"]
                source = "goose"
        elif self.goose_available and source == "ollama":
            # Ollama answered from training data; have Goose verify/enrich with live web data
            goose_result = _run_goose(goose_prompt, cwd=goose_cwd)
            if goose_result["ok"] and goose_result["stdout"]:
                # Prefer Goose output if it produced structured JSON; merge otherwise
                goose_parsed = _try_parse_json_from_text(goose_result["stdout"])
                if goose_parsed:
                    raw_text = goose_result["stdout"]
                    source = "goose+ollama"

        if not raw_text:
            result = {
                **fallback,
                "status": "no_response",
                "topic": topic,
                "generated_at": utc_now(),
                "note": "Local workers ran but produced no output.",
            }
            result_path.write_text(json.dumps(result, indent=2))
            return result

        try:
            extracted = extract_fn(raw_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ResearchWorker extract failed for %s: %s", topic, exc)
            extracted = {**fallback}

        result = {
            **extracted,
            "status": "researched",
            "topic": topic,
            "source": source,
            "generated_at": utc_now(),
            "fetched_at": utc_now(),
        }
        result_path.write_text(json.dumps(result, indent=2))
        logger.info("ResearchWorker: %s via %s → %s", topic, source, result_path.name)
        return result

    # ------------------------------------------------------------------
    # Extractors
    # ------------------------------------------------------------------

    def _extract_firmware_result(self, raw: str) -> dict[str, Any]:
        parsed = _try_parse_json_from_text(raw)
        if parsed:
            return {
                "firmware_sources": parsed.get("firmware_sources", []),
                "flash_procedure_hints": parsed.get("flash_procedure_hints", []),
                "lineageos_supported": parsed.get("lineageos_supported"),
                "twrp_supported": parsed.get("twrp_supported"),
                "grapheneos_supported": parsed.get("grapheneos_supported"),
                "unlock_procedure": parsed.get("unlock_procedure", ""),
                "anti_rollback_risk": parsed.get("anti_rollback_risk"),
                "community_notes": parsed.get("community_notes", ""),
                "confidence": float(parsed.get("confidence", 0.5)),
            }
        return {
            "firmware_sources": [],
            "flash_procedure_hints": [],
            "lineageos_supported": None,
            "twrp_supported": None,
            "grapheneos_supported": None,
            "unlock_procedure": "",
            "anti_rollback_risk": None,
            "community_notes": raw[:1000],
            "confidence": 0.3,
        }

    def _extract_device_result(self, raw: str) -> dict[str, Any]:
        parsed = _try_parse_json_from_text(raw)
        if parsed:
            return {
                "device_facts": parsed.get("device_facts", {}),
                "unlock_procedure": parsed.get("unlock_procedure", ""),
                "known_issues": parsed.get("known_issues", []),
                "recommended_approach": parsed.get("recommended_approach", "research_only"),
                "confidence": float(parsed.get("confidence", 0.5)),
            }
        return {
            "device_facts": {},
            "unlock_procedure": raw[:400],
            "known_issues": [],
            "recommended_approach": "research_only",
            "confidence": 0.25,
        }

    def _extract_blocker_result(self, raw: str) -> dict[str, Any]:
        parsed = _try_parse_json_from_text(raw)
        if parsed:
            return {
                "solutions": parsed.get("solutions", []),
                "next_steps": parsed.get("next_steps", []),
                "references": parsed.get("references", []),
                "confidence": float(parsed.get("confidence", 0.5)),
            }
        return {
            "solutions": [],
            "next_steps": [raw[:400]],
            "references": [],
            "confidence": 0.25,
        }

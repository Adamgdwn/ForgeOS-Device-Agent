from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


_OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")
_OLLAMA_MODEL = os.environ.get("FORGEOS_OLLAMA_MODEL", "gemma4:latest")
_DEFAULT_TIMEOUT = 120


class GemmaEngine:
    """Ollama HTTP API wrapper — structured decisions and device-specific codegen."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("forgeos.gemma")
        self.base_url = _OLLAMA_API_BASE.rstrip("/")
        self.model = _OLLAMA_MODEL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ask(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Return a structured JSON decision from Gemma."""
        system = (
            "You are the decision engine for ForgeOS, an autonomous Android device "
            "rehabilitation agent. Always respond with valid JSON and nothing else."
        )
        if schema:
            system += f"\n\nExpected JSON schema:\n{json.dumps(schema, indent=2)}"

        try:
            raw = self._http_generate(system, prompt, temperature)
            return self._parse_json(raw)
        except Exception as exc:
            self.logger.warning("Gemma HTTP ask failed (%s), trying subprocess", exc)
            return self._subprocess_ask(prompt)

    def write_code(
        self,
        task_description: str,
        device_context: dict[str, Any],
        language: str = "python",
    ) -> str:
        """Generate device-specific code. Returns empty string on failure."""
        system = (
            f"You are writing {language} code for ForgeOS, an autonomous Android device "
            "rehabilitation agent. Output ONLY the code — no explanation, no markdown "
            "fences, no comments unless they document a non-obvious constraint."
        )
        prompt = (
            f"Device context:\n{json.dumps(device_context, indent=2)}\n\n"
            f"Task:\n{task_description}\n\n"
            f"Write a complete, runnable {language} script that accomplishes this task "
            "for the specific device described above."
        )
        try:
            code = self._http_generate(system, prompt, temperature=0.3)
            code = _strip_markdown_fences(code)
            if language == "python":
                ast.parse(code)
            return code
        except SyntaxError as exc:
            self.logger.warning("Gemma returned invalid Python (%s) — using template", exc)
            return ""
        except Exception as exc:
            self.logger.warning("Gemma codegen failed (%s) — using template", exc)
            return ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _http_generate(self, system: str, prompt: str, temperature: float) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "system": system,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
        return body.get("response", "")

    def _subprocess_ask(self, prompt: str) -> dict[str, Any]:
        """Fallback: call ollama CLI. Returns empty dict on failure."""
        try:
            result = subprocess.run(
                ["ollama", "run", self.model, prompt, "--format", "json", "--hidethinking"],
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TIMEOUT,
                check=False,
            )
            return self._parse_json(result.stdout.strip())
        except Exception as exc:
            self.logger.error("Gemma subprocess fallback also failed: %s", exc)
            return {}

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return {}


def _strip_markdown_fences(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)

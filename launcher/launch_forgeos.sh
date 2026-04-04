#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
LOCAL_PLATFORM_TOOLS="${PROJECT_ROOT}/local-tools/platform-tools"

cd "${PROJECT_ROOT}"

if [ -d "${LOCAL_PLATFORM_TOOLS}" ]; then
  export PATH="${LOCAL_PLATFORM_TOOLS}:${PATH}"
fi

if command -v code >/dev/null 2>&1; then
  code "${PROJECT_ROOT}/forgeos.code-workspace" >/dev/null 2>&1 || true
else
  printf 'ForgeOS note: VS Code CLI `code` not found; continuing without workspace open.\n'
fi

if [ -x "${VENV_PYTHON}" ]; then
  exec "${VENV_PYTHON}" -m app.main
fi

exec python3 -m app.main

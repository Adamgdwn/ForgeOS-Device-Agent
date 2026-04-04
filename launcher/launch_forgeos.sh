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

# Desktop launches should prioritize the guided GUI, not a developer workspace.
export FORGEOS_OPEN_VSCODE="${FORGEOS_OPEN_VSCODE:-0}"

if [ -x "${VENV_PYTHON}" ]; then
  exec "${VENV_PYTHON}" -m app.main
fi

exec python3 -m app.main

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOCAL_PLATFORM_TOOLS="${PROJECT_ROOT}/local-tools/platform-tools"

cd "${PROJECT_ROOT}"
if [ -d "${LOCAL_PLATFORM_TOOLS}" ]; then
  export PATH="${LOCAL_PLATFORM_TOOLS}:${PATH}"
fi

if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
  "${PROJECT_ROOT}/.venv/bin/python" -c 'from pathlib import Path; from app.core.bootstrap import run_bootstrap; print(run_bootstrap(Path.cwd()))'
else
  python3 -c 'from pathlib import Path; from app.core.bootstrap import run_bootstrap; print(run_bootstrap(Path.cwd()))'
fi

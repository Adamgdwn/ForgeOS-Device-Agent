#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOCAL_PLATFORM_TOOLS="${PROJECT_ROOT}/local-tools/platform-tools"

if [ -d "${LOCAL_PLATFORM_TOOLS}" ]; then
  export PATH="${LOCAL_PLATFORM_TOOLS}:${PATH}"
fi

printf 'platform: %s\n' "$(uname -s)"
printf 'kernel: %s\n' "$(uname -r)"
printf 'code: %s\n' "$(command -v code || printf 'missing')"
printf 'adb: %s\n' "$(command -v adb || printf 'missing')"
printf 'fastboot: %s\n' "$(command -v fastboot || printf 'missing')"
printf 'python3: %s\n' "$(command -v python3 || printf 'missing')"
printf 'venv python: %s\n' "$([ -x "${PROJECT_ROOT}/.venv/bin/python" ] && printf '%s' "${PROJECT_ROOT}/.venv/bin/python" || printf 'missing')"

if [ -d /dev ] && [ -d /sys ]; then
  printf 'udev-like device paths: present\n'
else
  printf 'udev-like device paths: missing\n'
fi

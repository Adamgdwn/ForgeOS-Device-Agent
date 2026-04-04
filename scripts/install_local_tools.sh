#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "${PROJECT_ROOT}/downloads" "${PROJECT_ROOT}/local-tools"

if [ ! -f "${PROJECT_ROOT}/downloads/platform-tools-latest-linux.zip" ]; then
  curl -L --fail -o "${PROJECT_ROOT}/downloads/platform-tools-latest-linux.zip" \
    https://dl.google.com/android/repository/platform-tools-latest-linux.zip
fi

rm -rf "${PROJECT_ROOT}/local-tools/platform-tools"
unzip -q -o "${PROJECT_ROOT}/downloads/platform-tools-latest-linux.zip" -d "${PROJECT_ROOT}/local-tools"

printf 'Installed local platform-tools into %s\n' "${PROJECT_ROOT}/local-tools/platform-tools"

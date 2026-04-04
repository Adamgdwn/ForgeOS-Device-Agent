#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${HOME}/.local/share/applications"
TEMPLATE="${PROJECT_ROOT}/launcher/forgeos.desktop"
TARGET_FILE="${TARGET_DIR}/forgeos.desktop"
EXEC_PATH="${PROJECT_ROOT}/launcher/launch_forgeos.sh"
ICON_PATH="${PROJECT_ROOT}/launcher/icon.png"

mkdir -p "${TARGET_DIR}"
chmod +x "${PROJECT_ROOT}/launcher/launch_forgeos.sh"
cat > "${TARGET_FILE}" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ForgeOS Device Agent
Comment=Assess and orchestrate Android device build sessions
Exec="${EXEC_PATH}"
Icon=${ICON_PATH}
Terminal=false
Categories=Development;Utility;
StartupNotify=true
EOF

printf 'Installed ForgeOS launcher to %s\n' "${TARGET_FILE}"

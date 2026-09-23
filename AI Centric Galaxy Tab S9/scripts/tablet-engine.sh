#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
umask 077
cd /data/data/com.termux/files/home/galaxy-workspace
mkdir -p .local
if [[ "${1:-}" == "--pair" ]]; then
  export GALAXY_RUNTIME=android GALAXY_ORIGIN=http://localhost:4318
  exec node scripts/tablet-pair.ts
fi
[[ $# == 0 ]] || exit 2
exec 9>.local/engine.lock
flock -n 9 || exit 0
export GALAXY_RUNTIME=android
export GALAXY_ORIGIN=http://localhost:4318
export GALAXY_CODEX_BIN="$PWD/scripts/tablet-codex.sh"
export CODEX_HOME="$PWD/.local/codex-home"
export GALAXY_PDF_ENGINE=typst
export OMP_NUM_THREADS=1
termux-wake-lock
tablet_engine_pid=
cleanup() {
  if [[ -n "$tablet_engine_pid" ]]; then kill -TERM "$tablet_engine_pid" 2>/dev/null || true; wait "$tablet_engine_pid" || true; fi
  termux-wake-unlock
}
trap cleanup EXIT
trap 'exit 0' TERM INT
node server/main.ts >>.local/engine.log 2>&1 &
tablet_engine_pid=$!
wait "$tablet_engine_pid"

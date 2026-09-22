#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../android"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
case "${1:-build}" in
  build)
    # One bounded build, one Gradle worker and a 2 GB JVM (gradle.properties).
    exec timeout --signal=TERM --kill-after=20s 10m ./gradlew --no-daemon --max-workers=1 --console=plain :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :reader:assembleDebug :reader:lintDebug
    ;;
  install)
    tablet_serial="${2:?Usage: ./galaxy android-install DEVICE_SERIAL}"
    tablet_adb="$ANDROID_HOME/platform-tools/adb"
    tablet_apk="app/build/outputs/apk/debug/app-debug.apk"
    [[ -x "$tablet_adb" ]] || { echo "ADB not found in ANDROID_HOME/platform-tools." >&2; exit 1; }
    [[ -f "$tablet_apk" ]] || { echo "Run ./galaxy android-build first." >&2; exit 1; }
    [[ -f reader/build/outputs/apk/debug/reader-debug.apk ]] || { echo "Run ./galaxy android-build to build the Outlook reader." >&2; exit 1; }
    "$tablet_adb" -s "$tablet_serial" get-state
    "$tablet_adb" -s "$tablet_serial" install -r "$tablet_apk"
    "$tablet_adb" -s "$tablet_serial" install -r reader/build/outputs/apk/debug/reader-debug.apk
    "$tablet_adb" -s "$tablet_serial" reverse tcp:4318 tcp:4318
    "$tablet_adb" -s "$tablet_serial" shell am start -n com.adamgoodwin.galaxyworkspace/.MainActivity
    ;;
  *) echo 'Expected build or install DEVICE_SERIAL.' >&2; exit 2 ;;
esac

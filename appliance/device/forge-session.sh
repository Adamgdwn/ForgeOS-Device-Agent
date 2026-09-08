#!/system/bin/sh
# SM-T377W session lifecycle. Appliance mode is started by the on-device launcher.
set -eu
umask 077

usage() { echo "usage: $0 /absolute/forge-install seconds(1..1800)|appliance" >&2; exit 64; }
install=${1-}
seconds=${2-}
[ "$#" -eq 2 ] || usage
case "$install" in /*) ;; *) usage;; esac
if [ "$seconds" = appliance ]; then
  set -- --appliance
else
  case "$seconds" in ''|*[!0-9]*) usage;; esac
  [ "$seconds" -ge 1 ] && [ "$seconds" -le 1800 ] || usage
  set -- --seconds "$seconds"
fi
if [ "$seconds" = appliance ]; then
  [ -r "$install/forge-surface.jar" ] && [ -r "$install/libforge-panel.so" ] &&
    command -v app_process >/dev/null || exit 77
fi

root="$install/linux-root"
lock="$install/.forge-session.lock"
for path in "$install/forge-panel" "$install/forge-namespace-run" \
  "$root/usr/local/bin/forge-browser-session" "$root/usr/local/bin/forge-music-bridge" \
  "$root/usr/bin/Xvfb" "$root/usr/lib/chromium/chromium" \
  "$root/opt/forge/forge-alsa-compat.so"; do
  [ -e "$path" ] || { echo "missing prerequisite: $path" >&2; exit 77; }
done
[ -x "$install/forge-panel" ] && [ -x "$install/forge-namespace-run" ] &&
  [ -x "$root/usr/local/bin/forge-browser-session" ] &&
  [ -r "$install/forge-cdp-guard.sh" ] || exit 77
. "$install/forge-cdp-guard.sh" || exit 77
[ -d "$root" ] && command -v tinymix >/dev/null && command -v start >/dev/null && command -v stop >/dev/null && command -v ip >/dev/null && command -v dumpsys >/dev/null || exit 77
if pidof forge-panel forge-namespace-run >/dev/null 2>&1; then
  echo "A Forge panel or namespace supervisor is already running" >&2
  exit 75
fi
mkdir "$lock" 2>/dev/null || { echo "Forge session already active or stale lock: $lock" >&2; exit 75; }
chmod 700 "$lock"
printf '%s\n' "$$" > "$lock/session.pid"
awk '{ print $22 }' "/proc/$$/stat" > "$lock/session.start"

service= panel= namespace=
zygote_was= surfaceflinger_was= audioserver_was= netd_was=
wlan_default_route=
services_stopped=0
audio_configured=0
framework_stopped=0
restore_failed=0
mark_restore_failure() {
  echo "Forge cleanup failed: $1" >&2
  restore_failed=1
}
wait_service_state() {
  wait_service=$1
  wait_state=$2
  wait_count=0
  while [ "$wait_count" -lt 50 ]; do
    [ "$(getprop "init.svc.$wait_service")" = "$wait_state" ] && return 0
    sleep 0.1
    wait_count=$((wait_count + 1))
  done
  mark_restore_failure "$wait_service did not become $wait_state within 5 seconds"
  return 1
}
wait_wlan_network() {
  wait_count=0
  while [ "$wait_count" -lt 60 ]; do
    # A leftover route can exist briefly before the new framework reconnects.
    # Require the current Wi-Fi agent's validation, not historical log entries.
    if ip -4 route show table wlan0 2>/dev/null | awk '$1 == "default" { found=1 } END { exit !found }' &&
       dumpsys -t 1 connectivity 2>/dev/null | awk '
         /^[[:space:]]*NetworkAgentInfo[{]/ && index($0, "type: WIFI") &&
         index($0, "lastValidated{true}") { found=1 }
         END { exit !found }'; then
      return 0
    fi
    sleep 1
    wait_count=$((wait_count + 1))
  done
  mark_restore_failure "wlan0 route and internet validation did not return within 60 recovery polls"
  return 1
}
restore_services() {
  # system_server keeps Wi-Fi alive during appliance mode, but its cached
  # SurfaceComposer handles must be recreated after SurfaceFlinger was stopped.
  if [ "$zygote_was" = running ] && [ "$framework_stopped" = 0 ]; then
    stop zygote >/dev/null 2>&1 || mark_restore_failure "could not stop stale Android framework"
    wait_service_state zygote stopped || true
    framework_stopped=1
  fi
  if [ "$framework_stopped" = 1 ] && [ "$netd_was" = running ] && [ "$zygote_was" = running ]; then
    stop netd >/dev/null 2>&1 || mark_restore_failure "could not stop netd"
    wait_service_state netd stopped || true
    start netd >/dev/null 2>&1 || mark_restore_failure "could not start netd"
    wait_service_state netd running || true
  fi
  if [ "$framework_stopped" = 1 ] && [ "$zygote_was" = running ]; then
    start zygote >/dev/null 2>&1 || mark_restore_failure "could not start zygote"
    wait_service_state zygote running || true
  fi
  if [ "$surfaceflinger_was" = running ]; then
    start surfaceflinger >/dev/null 2>&1 || mark_restore_failure "could not start surfaceflinger"
    wait_service_state surfaceflinger running || true
  fi
  if [ "$audioserver_was" = running ]; then
    start audioserver >/dev/null 2>&1 || mark_restore_failure "could not start audioserver"
    wait_service_state audioserver running || true
  fi
  if [ "$zygote_was" = running ] && [ -n "$wlan_default_route" ]; then
    wait_wlan_network || true
  fi
}
quiet_mixer_cleanup() {
  tinymix 'AudioMixer Mixer En' 0; tinymix 'AudioMixer SRC1 En' 0
  tinymix 'AudioMixer SRC2 En' 0; tinymix 'AudioMixer SRC3 En' 0
  tinymix 'AudioMixer CH1 Mixer En' 0; tinymix 'AudioMixer CH2 Mixer En' 0
  tinymix 'AudioMixer CH3 Mixer En' 0; tinymix 'AudioMixer CH4 Mixer En' 0
  tinymix 'AudioMixer CH1 DOUT Select' DMIX_OUT; tinymix 'MonoMix Mode' Disable
  tinymix 'Chargepump Mode' CLASS-G-A; tinymix 'DNC Max Gain' 24
  tinymix 'HP HP On' 0; tinymix 'EP EP On' 0; tinymix 'SPK SPK On' 0
  tinymix 'AudioMixer MIX1_LVL' 0; tinymix 'DAC Gain' 127 127; tinymix 'Speaker Volume' 3
}
cleanup() {
  original_status=$?
  [ -z "$panel" ] || kill -TERM "$panel" 2>/dev/null || true
  [ -z "$service" ] || kill -TERM "$service" 2>/dev/null || true
  [ -z "$panel" ] || wait "$panel" 2>/dev/null || true
  [ -z "$service" ] || wait "$service" 2>/dev/null || true
  forge_cdp_stop
  if [ "$audio_configured" = 1 ]; then
    quiet_mixer_cleanup >/dev/null 2>&1 || true
  fi
  if [ "$services_stopped" = 1 ]; then
    restore_services
  fi
  rm -f "$lock/session.pid" "$lock/session.start" "$lock/service.pid" "$lock/service.start" "$lock/panel.pid" "$lock/panel.start" "$lock/ready" "$lock/display.mode"
  rmdir "$lock" 2>/dev/null || true
  if [ "$restore_failed" = 1 ]; then
    echo "Forge cleanup completed with restoration failures" >&2
    exit 70
  fi
  exit "$original_status"
}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM

# Check the route before Android graphics/services are stopped.
tinymix 'AudioMixer Mixer En' >/dev/null 2>&1 || exit 77
zygote_was=$(getprop init.svc.zygote)
surfaceflinger_was=$(getprop init.svc.surfaceflinger)
audioserver_was=$(getprop init.svc.audioserver)
netd_was=$(getprop init.svc.netd)
wlan_default_route=$(ip -4 route show table wlan0 2>/dev/null | awk '$1 == "default" { print; exit }')
[ -n "$wlan_default_route" ] || { echo "No wlan0 IPv4 default route; refusing online Forge session" >&2; exit 69; }
if [ "$seconds" = appliance ]; then
  [ "$zygote_was" = running ] && [ "$surfaceflinger_was" = running ] &&
    [ "$audioserver_was" = running ] && [ "$netd_was" = running ] || exit 69
  dumpsys -t 1 connectivity 2>/dev/null | awk '
    /^[[:space:]]*NetworkAgentInfo[{]/ && index($0,"type: WIFI") &&
    index($0,"lastValidated{true}") {found=1} END {exit !found}' || exit 69
fi
forge_cdp_start || exit 77
input keyevent 224 >/dev/null 2>&1 || true
if [ "$seconds" != appliance ]; then
  services_stopped=1
  framework_stopped=1
  stop zygote
  stop surfaceflinger; stop audioserver
  sleep 2
  echo 0 > /sys/class/graphics/fb0/blank
else
  printf '%s\n' surface > "$lock/display.mode"
fi
audio_configured=1
tinymix 'AudioMixer Mixer En' On; tinymix 'AudioMixer SRC1 En' Off
tinymix 'AudioMixer SRC2 En' Off; tinymix 'AudioMixer SRC3 En' Off
tinymix 'AudioMixer CH1 Mixer En' On; tinymix 'AudioMixer CH2 Mixer En' Off
tinymix 'AudioMixer CH3 Mixer En' Off; tinymix 'AudioMixer CH4 Mixer En' Off
tinymix 'AudioMixer CH1 DOUT Select' AIF4IN; tinymix 'MonoMix Mode' Disable
tinymix 'Chargepump Mode' CLASS-G-A; tinymix 'DNC Max Gain' 24
tinymix 'HP HP On' 0; tinymix 'EP EP On' 0; tinymix 'SPK SPK On' 1
tinymix 'AudioMixer MIX1_LVL' 0; tinymix 'DAC Gain' 114; tinymix 'Speaker Volume' 3

"$install/forge-namespace-run" --root "$root" "$@" --audio -- \
  /usr/local/bin/forge-browser-session "$seconds" >/dev/null 2>&1 &
service=$!
printf '%s\n' "$service" > "$lock/service.pid"
awk '{ print $22 }' "/proc/$service/stat" > "$lock/service.start"
for n in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50; do
  namespace=$(ps -A -o PID,PPID 2>/dev/null | awk -v p="$service" '$2==p {print $1; exit}')
  kill -0 "$service" 2>/dev/null || exit 1
  [ -n "$namespace" ] && [ -e "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" ] && break
  sleep 0.1
done
[ -n "$namespace" ] || exit 1
[ -e "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" ] || exit 1
set --
home_url=
if [ -r "$root/etc/forge/home.url" ]; then IFS= read -r home_url < "$root/etc/forge/home.url" || true; fi
case "$home_url" in http://*|https://*) set -- --home-dashboard;; esac
if [ "$seconds" = appliance ]; then
  has_home=0
  [ "$#" = 0 ] || has_home=1
  # The broker deliberately clears its environment. ART needs the ROM's boot
  # jars and APEX paths even though ordinary native executables do not.
  # Read only the two fixed classpath fields, without evaluating init syntax.
  export ANDROID_ROOT=/system ANDROID_DATA=/data
  export ANDROID_RUNTIME_ROOT=/apex/com.android.runtime ANDROID_TZDATA_ROOT=/apex/com.android.tzdata
  BOOTCLASSPATH=$(awk '$1=="export" && $2=="BOOTCLASSPATH" {print $3; exit}' /init.environ.rc)
  DEX2OATBOOTCLASSPATH=$(awk '$1=="export" && $2=="DEX2OATBOOTCLASSPATH" {print $3; exit}' /init.environ.rc)
  [ -n "$BOOTCLASSPATH" ] && [ -n "$DEX2OATBOOTCLASSPATH" ] || exit 77
  export BOOTCLASSPATH DEX2OATBOOTCLASSPATH
  CLASSPATH="$install/forge-surface.jar" app_process /system/bin --nice-name=forge-panel \
    org.forge.surface.ForgeSurface "$install" "$root/var/lib/forge/control/music.sock" \
    "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" \
    "/proc/$namespace/root/tmp/.X11-unix/X7" "$has_home" >/dev/null 2>&1 &
else
  "$install/forge-panel" --music-service \
  "$@" \
  --socket "$root/var/lib/forge/control/music.sock" --fb /dev/graphics/fb0 --samsung \
  --input /dev/input/event1 --web-surface "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" \
  --x11-socket "/proc/$namespace/root/tmp/.X11-unix/X7" >/dev/null 2>&1 &
fi
panel=$!
printf '%s\n' "$panel" > "$lock/panel.pid"
awk '{ print $22 }' "/proc/$panel/stat" > "$lock/panel.start"
: > "$lock/ready"
# Android's retained framework owns Wi-Fi reconnection. Its external validation
# probe can time out while music or the local dashboard still works; losing that
# probe must not tear down the browser, account session, or native controls.
while kill -0 "$service" 2>/dev/null; do
  if ! kill -0 "$panel" 2>/dev/null; then
    if wait "$panel"; then panel=; exit 0; else panel=; exit 1; fi
  fi
  sleep 1
done
if wait "$service"; then result=0; else result=$?; fi
service=
exit "$result"

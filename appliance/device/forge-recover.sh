#!/system/bin/sh
# Fixed recovery for the on-device appliance broker. Never starts Forge.
set -eu
install=${1-}
[ "$#" -eq 1 ] || exit 64
case "$install" in /*) ;; *) exit 64;; esac
lock="$install/.forge-session.lock"
failed=0
session_pid=
had_session=0
surface_session=0
if [ -d "$lock" ]; then had_session=1; fi
if [ -f "$lock/display.mode" ] && [ "$(cat "$lock/display.mode")" = surface ]; then surface_session=1; fi
if [ -f "$lock/session.pid" ]; then session_pid=$(cat "$lock/session.pid"); fi
case "$session_pid" in ''|*[!0-9]*) session_pid=;; esac

record_alive() {
  record=$1
  [ -f "$lock/$record.pid" ] && [ -f "$lock/$record.start" ] || return 1
  record_pid=$(cat "$lock/$record.pid")
  record_start=$(cat "$lock/$record.start")
  case "$record_pid:$record_start" in *[!0-9:]*|:*|*:) return 1;; esac
  [ "$record_pid" -gt 1 ] || return 1
  [ -r "/proc/$record_pid/stat" ] || return 1
  current_start=$(awk '{ print $22 }' "/proc/$record_pid/stat" 2>/dev/null || true)
  [ "$current_start" = "$record_start" ]
}
terminate_record() {
  record=$1
  record_alive "$record" || return 0
  kill -TERM "$record_pid" 2>/dev/null || true
  count=0
  while [ "$count" -lt 50 ]; do
    record_alive "$record" || return 0
    sleep 0.1; count=$((count+1))
  done
  # Revalidate starttime immediately before escalation: a reused PID is not ours.
  if record_alive "$record"; then kill -KILL "$record_pid" 2>/dev/null || true; fi
}
terminate_record session
terminate_record panel
terminate_record service
sleep 1
if pidof forge-panel forge-namespace-run >/dev/null 2>&1; then
  echo "Recovery is waiting for an existing Forge process" >&2
  exit 70
fi

# SIGKILL of a namespace can prevent the bridge from unlinking its socket.
# The service tree is now gone. Remove only that owned socket, refusing links
# and unexpected objects so recovery cannot follow browser-controlled paths.
cleanup_music_socket() {
  control="$install/linux-root/var/lib/forge/control"
  for path in "$install/linux-root/var" "$install/linux-root/var/lib" \
    "$install/linux-root/var/lib/forge" "$control"; do
    [ ! -L "$path" ] && [ -d "$path" ] || {
      echo "Unexpected music control directory during recovery" >&2; return 1;
    }
  done
  music_socket="$control/music.sock"
  if [ -e "$music_socket" ] || [ -L "$music_socket" ]; then
    [ ! -L "$music_socket" ] && [ -S "$music_socket" ] &&
      [ "$(stat -c %u "$music_socket")" = 65000 ] || {
        echo "Unexpected music control object during recovery" >&2; return 1;
      }
    rm "$music_socket" || return 1
  fi
}
cleanup_music_socket || failed=1

. "$install/forge-cdp-guard.sh"
if [ -n "$session_pid" ]; then
  forge_cdp_chain="FORGE_CDP_$session_pid"
  forge_cdp_v4=1; forge_cdp_v6=1
  forge_cdp_stop
fi
# These are the same known quiet mixer defaults as normal session shutdown.
tinymix 'AudioMixer Mixer En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer SRC1 En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer SRC2 En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer SRC3 En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer CH1 Mixer En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer CH2 Mixer En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer CH3 Mixer En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer CH4 Mixer En' 0 >/dev/null 2>&1 || true
tinymix 'AudioMixer CH1 DOUT Select' DMIX_OUT >/dev/null 2>&1 || true
tinymix 'SPK SPK On' 0 >/dev/null 2>&1 || true
tinymix 'HP HP On' 0 >/dev/null 2>&1 || true
tinymix 'EP EP On' 0 >/dev/null 2>&1 || true
tinymix 'DAC Gain' 127 127 >/dev/null 2>&1 || true
tinymix 'Speaker Volume' 3 >/dev/null 2>&1 || true

# Recreate cached SurfaceComposer handles after takeover; merely starting
# SurfaceFlinger can leave a live system_server unable to create any windows.
if { [ "$had_session" = 1 ] && [ "$surface_session" = 0 ]; } ||
   [ "$(getprop init.svc.zygote)" != running ]; then
  stop zygote >/dev/null 2>&1 || true
  stop netd >/dev/null 2>&1 || true
  sleep 1
  start netd >/dev/null 2>&1 || true
  start zygote >/dev/null 2>&1 || true
fi
start surfaceflinger >/dev/null 2>&1 || true
start audioserver >/dev/null 2>&1 || true
count=0
while [ "$count" -lt 60 ]; do
  if [ "$(getprop init.svc.zygote)" = running ] &&
     [ "$(getprop init.svc.surfaceflinger)" = running ] &&
     [ "$(getprop init.svc.audioserver)" = running ] &&
     ip -4 route show table wlan0 2>/dev/null | awk '$1=="default" {found=1} END {exit !found}' &&
     dumpsys -t 1 connectivity 2>/dev/null | awk '
       /^[[:space:]]*NetworkAgentInfo[{]/ && index($0,"type: WIFI") &&
       index($0,"lastValidated{true}") {found=1} END {exit !found}'; then
    break
  fi
  sleep 1; count=$((count+1))
done
[ "$count" -lt 60 ] || failed=1
for tool in iptables ip6tables; do
  if "$tool" -S OUTPUT 2>/dev/null | toybox grep -q FORGE_CDP_; then failed=1; fi
done
rm -f "$lock/session.pid" "$lock/session.start" "$lock/service.pid" "$lock/service.start" "$lock/panel.pid" "$lock/panel.start" "$lock/ready" "$lock/display.mode"
rmdir "$lock" 2>/dev/null || true
[ "$failed" = 0 ] || { echo "Android restored with network or cleanup pending" >&2; exit 70; }
input keyevent 224 >/dev/null 2>&1 || true
wm dismiss-keyguard >/dev/null 2>&1 || true
launch_result=$(am start -W -n org.forge.appliance/.ForgeActivity 2>&1) || {
  echo "Android window system could not open the Forge launcher" >&2; exit 70;
}
case "$launch_result" in *'Status: ok'*) ;; *) echo "Launcher window was not confirmed" >&2; exit 70;; esac
echo "Android display, audio and validated Wi-Fi restored"

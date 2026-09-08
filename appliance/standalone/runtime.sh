#!/bin/sh
# Own one browser namespace and its direct framebuffer frontend.
set -eu
umask 077
base=/data/forge
root=/os/root
bb=/bin/busybox
mkdir /run/forge-runtime.lock 2>/dev/null || exit 1
service= panel=
cleanup() {
  [ -z "$panel" ] || kill -TERM "$panel" 2>/dev/null || true
  [ -z "$service" ] || kill -TERM "$service" 2>/dev/null || true
  [ -z "$panel" ] || wait "$panel" 2>/dev/null || true
  [ -z "$service" ] || wait "$service" 2>/dev/null || true
  "$bb" rmdir /run/forge-runtime.lock 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM
count=0
while [ "$count" -lt 20 ] && [ ! -e /run/forge-network-ready ]; do
  count=$((count+1)); sleep 1
done
/bin/sh /etc/forge/audio-route.sh
if "$bb" pidof forge-namespace-run >/dev/null; then
  echo 'Existing browser namespace must finish before startup'; exit 1
fi
socket="$root/var/lib/forge/control/music.sock"
if [ -e "$socket" ] || [ -L "$socket" ]; then
  [ -S "$socket" ] && [ ! -L "$socket" ] && [ "$("$bb" stat -c %u "$socket")" = 65000 ] || exit 1
  "$bb" rm "$socket"
fi
for name in SingletonLock SingletonCookie SingletonSocket; do
  path="$root/var/lib/forge/browser/profile/$name"
  [ ! -L "$path" ] || "$bb" rm "$path"
done
/sbin/forge-namespace-run --root "$root" --appliance --audio -- \
  /usr/local/bin/forge-browser-session appliance >"$base/browser.log" 2>&1 &
service=$!
printf '%s\n' "$service" > /run/forge-browser.pid
namespace=
count=0
while [ "$count" -lt 60 ]; do
  kill -0 "$service" 2>/dev/null || { echo 'Browser namespace exited'; exit 1; }
  for p in /proc/[0-9]*/stat; do
    parent=$("$bb" awk '{print $4}' "$p" 2>/dev/null || true)
    if [ "$parent" = "$service" ]; then
      namespace=${p#/proc/}; namespace=${namespace%/stat}; break
    fi
  done
  [ -n "$namespace" ] && [ -e "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" ] && break
  count=$((count+1)); sleep 1
done
[ -n "$namespace" ] && [ -e "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" ] || exit 1
if [ -r /run/forge-panel.pid ]; then
  IFS= read -r old_panel < /run/forge-panel.pid
  case "$old_panel" in ''|*[!0-9]*) exit 1;; esac
  kill -TERM "$old_panel" 2>/dev/null || true
  sleep 1
fi
start_panel() {
  /sbin/forge-panel --standalone --music-service --home-dashboard \
  --status-file /run/forge-panel.status \
  --socket "$root/var/lib/forge/control/music.sock" --fb /dev/graphics/fb0 --samsung \
  --input /dev/input/event1 --web-surface "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" \
  --x11-socket "/proc/$namespace/root/tmp/.X11-unix/X7" >"$base/panel.log" 2>&1 &
  panel=$!
  printf '%s\n' "$panel" > /run/forge-panel.pid
}
start_panel
echo 'Forge display connected to Linux music and home services'
failures=0
while kill -0 "$service" 2>/dev/null; do
  if ! kill -0 "$panel" 2>/dev/null; then
    wait "$panel" 2>/dev/null || true
    failures=$((failures+1))
    echo 'Restarting display; browser and music remain running'
    if [ "$failures" -gt 3 ]; then sleep 10; else sleep 1; fi
    start_panel
  fi
  sleep 1
done
echo 'Forge runtime child exited'
exit 1

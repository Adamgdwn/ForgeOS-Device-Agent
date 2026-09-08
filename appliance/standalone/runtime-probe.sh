#!/bin/sh
# Standalone hardware integration, bounded by the init probe's recovery timer.
set -eu
umask 077
base=/data/forge-standalone
install=/data/local/tmp/forge-native.mdJ5BP
root="$install/linux-root"
bb=/bin/busybox
mkdir /run/forge-runtime.lock 2>/dev/null || { echo 'Forge runtime already owned'; exit 1; }
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
/bin/sh "$base/network-probe.sh"
"$bb" cp /etc/resolv.conf "$root/etc/resolv.conf"
"$bb" chmod 644 "$root/etc/resolv.conf"
/bin/sh "$base/audio-route.sh"
# A new standalone boot changes the host identity recorded by Chromium.
# Only remove its three transient symlinks after proving no browser namespace
# is alive and acquiring the one global runtime lock. Never read profile data.
if "$bb" pidof forge-namespace-run >/dev/null; then
  echo 'Existing browser namespace must finish before startup'; exit 1
fi
for name in SingletonLock SingletonCookie SingletonSocket; do
  path="$root/var/lib/forge/browser/profile/$name"
  [ ! -L "$path" ] || "$bb" rm "$path"
done
"$install/forge-namespace-run" --root "$root" --appliance --audio -- \
  /usr/local/bin/forge-browser-session appliance >"$base/browser-probe.log" 2>&1 &
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
echo "Linux browser surface ready; namespace=$namespace"
if [ -r /run/forge-panel.pid ]; then
  IFS= read -r old_panel < /run/forge-panel.pid
  case "$old_panel" in ''|*[!0-9]*) exit 1;; esac
  kill -TERM "$old_panel" 2>/dev/null || true
  sleep 1
fi
/sbin/forge-panel --music-service --home-dashboard \
  --socket "$root/var/lib/forge/control/music.sock" --fb /dev/graphics/fb0 --samsung \
  --input /dev/input/event1 --web-surface "/proc/$namespace/root/tmp/forge-surface/Xvfb_screen0" \
  --x11-socket "/proc/$namespace/root/tmp/.X11-unix/X7" >"$base/panel-live.log" 2>&1 &
panel=$!
printf '%s\n' "$panel" > /run/forge-panel.pid
echo 'Forge display connected to independent Linux browser and audio'
while kill -0 "$service" 2>/dev/null && kill -0 "$panel" 2>/dev/null; do sleep 1; done
echo 'Forge runtime child exited'
exit 1

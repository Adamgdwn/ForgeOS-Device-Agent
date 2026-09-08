#!/bin/sh
# Private Linux-side browser session. Invoked only by forge-namespace-run.
set -eu
umask 077

seconds=${1-}
if [ "$seconds" = appliance ]; then
  set -- --appliance
else
  case "$seconds" in ''|*[!0-9]*) exit 64;; esac
  [ "$seconds" -ge 1 ] && [ "$seconds" -le 1800 ] || exit 64
  set -- --seconds "$seconds"
fi

export DISPLAY=:7 HOME=/var/lib/forge/browser
profile=/var/lib/forge/browser/profile
control=/var/lib/forge/control
mkdir -p "$profile" "$control" /tmp/forge-surface
chmod 700 /var/lib/forge /var/lib/forge/browser "$profile" "$control"

xpid= browser= bridge=
cleanup() {
  [ -z "$bridge" ] || kill -TERM "$bridge" 2>/dev/null || true
  [ -z "$browser" ] || kill -TERM "$browser" 2>/dev/null || true
  [ -z "$xpid" ] || kill -TERM "$xpid" 2>/dev/null || true
  [ -z "$bridge" ] || wait "$bridge" 2>/dev/null || true
  [ -z "$browser" ] || wait "$browser" 2>/dev/null || true
  [ -z "$xpid" ] || wait "$xpid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM

/usr/bin/Xvfb :7 -screen 0 800x1040x24 -nolisten tcp -nolisten local -ac \
  -fbdir /tmp/forge-surface >"$control/xvfb.log" 2>&1 &
xpid=$!
sleep 1
kill -0 "$xpid" 2>/dev/null || exit 1

set -- https://music.youtube.com
home_url=
if [ -r /etc/forge/home.url ]; then IFS= read -r home_url < /etc/forge/home.url || true; fi
case "$home_url" in http://*|https://*) set -- "$@" "$home_url";; esac
LD_PRELOAD=/opt/forge/forge-alsa-compat.so /usr/lib/chromium/chromium \
  --no-sandbox --no-first-run --no-default-browser-check --hide-crash-restore-bubble --disable-gpu \
  --disable-software-rasterizer --disable-dev-shm-usage \
  --user-data-dir="$profile" --renderer-process-limit=2 \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port=9224 \
  --alsa-output-device=plughw:0,0 --window-size=800,1040 \
  "$@" >"$control/chromium.log" 2>&1 &
browser=$!
if [ "$seconds" = appliance ]; then set -- --appliance; else set -- --seconds "$seconds"; fi
start_bridge() {
  /usr/local/bin/forge-music-bridge --socket "$control/music.sock" \
  --cdp-port 9224 "$@" >"$control/bridge.log" 2>&1 &
  bridge=$!
}
start_bridge "$@"
bridge_failures=0
while kill -0 "$browser" 2>/dev/null; do
  kill -0 "$xpid" 2>/dev/null || { echo 'X display exited'; exit 1; }
  if ! kill -0 "$bridge" 2>/dev/null; then
    wait "$bridge" 2>/dev/null || true
    bridge_failures=$((bridge_failures+1))
    [ "$bridge_failures" -le 3 ] || { echo 'Music bridge failed repeatedly'; exit 1; }
    if [ -e "$control/music.sock" ] || [ -L "$control/music.sock" ]; then
      [ -S "$control/music.sock" ] && [ ! -L "$control/music.sock" ] || exit 1
      rm "$control/music.sock"
    fi
    echo 'Restarting music controls; browser and audio remain running'
    start_bridge "$@"
  fi
  sleep 1
done
status=0
wait "$browser" || status=$?
echo "Browser exited with status $status"
exit "$status"

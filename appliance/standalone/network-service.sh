#!/bin/sh
# Linux owns association and DHCP renewal; no Android network service.
set -eu
umask 077
base=/data/forge
tools="$base/network"
bb=/bin/busybox
loader="$tools/usr/lib/ld-linux-armhf.so.3"
libs="$tools/usr/lib/arm-linux-gnueabihf"
wpa= dhcp=
cleanup() {
  [ -z "$dhcp" ] || kill -TERM "$dhcp" 2>/dev/null || true
  [ -z "$wpa" ] || kill -TERM "$wpa" 2>/dev/null || true
  [ -z "$dhcp" ] || wait "$dhcp" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' HUP INT TERM
echo "$base/firmware/bcmdhd_sta.bin" > /sys/module/dhd/parameters/firmware_path
echo "$base/firmware/nvram_net.txt" > /sys/module/dhd/parameters/nvram_path
cat /proc/deferred_initcalls >/dev/null
"$bb" ip link set lo up
mkdir -p /run/wpa_supplicant
[ -r "$base/wpa_supplicant.conf" ]
"$loader" --library-path "$libs" "$tools/usr/sbin/wpa_supplicant" \
  -B -i wlan0 -D nl80211 -c "$base/wpa_supplicant.conf" \
  -P /run/forge-wpa.pid -f /run/forge-wpa.log >/dev/null 2>&1
IFS= read -r wpa < /run/forge-wpa.pid
case "$wpa" in ''|*[!0-9]*) exit 1;; esac
"$bb" udhcpc -f -i wlan0 -s /etc/forge/dhcp-event.sh \
  -p /run/forge-dhcp.pid -t 4 -T 3 -A 10 > /run/forge-dhcp.log 2>&1 &
dhcp=$!
echo 'Linux Wi-Fi and DHCP renewal services started'
while kill -0 "$wpa" 2>/dev/null && kill -0 "$dhcp" 2>/dev/null; do sleep 5; done
echo 'Network service exited; supervisor will restart it'
exit 1

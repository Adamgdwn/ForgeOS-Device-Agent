#!/bin/sh
# Independent Linux network startup. Secret configuration stays on the tablet.
set -eu
umask 077
base=/data/forge-standalone
tools="$base/network"
bb=/bin/busybox
loader="$tools/usr/lib/ld-linux-armhf.so.3"
libs="$tools/usr/lib/arm-linux-gnueabihf"

echo "$base/firmware/bcmdhd_sta.bin" > /sys/module/dhd/parameters/firmware_path
echo "$base/firmware/nvram_net.txt" > /sys/module/dhd/parameters/nvram_path
cat /proc/deferred_initcalls >/dev/null
$bb ip link set lo up
mkdir -p /run/wpa_supplicant
[ -r "$base/wpa_supplicant.conf" ]
existing=
[ ! -r /run/forge-wpa.pid ] || IFS= read -r existing < /run/forge-wpa.pid
case "$existing" in ''|*[!0-9]*) existing=;; esac
if [ -z "$existing" ] || ! kill -0 "$existing" 2>/dev/null; then
  "$loader" --library-path "$libs" "$tools/usr/sbin/wpa_supplicant" \
  -B -i wlan0 -D nl80211 -c "$base/wpa_supplicant.conf" \
    -P /run/forge-wpa.pid -f "$base/wpa-probe.log" >/dev/null 2>&1
fi
echo 'Linux Wi-Fi supplicant started'
count=0
while [ "$count" -lt 45 ]; do
  state=$("$loader" --library-path "$libs" "$tools/usr/sbin/wpa_cli" \
    -p /run/wpa_supplicant -i wlan0 status 2>/dev/null | "$bb" grep '^wpa_state=' || true)
  if [ "$state" = wpa_state=COMPLETED ]; then break; fi
  count=$((count+1)); sleep 1
done
[ "$state" = wpa_state=COMPLETED ] || { echo 'Wi-Fi association did not complete'; exit 1; }
echo 'Wi-Fi association completed'
chmod 700 "$base/dhcp-event.sh"
"$bb" udhcpc -i wlan0 -s "$base/dhcp-event.sh" -n -q -t 4 -T 3 > "$base/dhcp-probe.log" 2>&1
echo 'DHCP completed'

#!/bin/sh
set -eu
bb=/bin/busybox
[ "${interface-}" = wlan0 ] || exit 1
case "${ip-}${subnet-}${router-}${dns-}" in *[!0-9.\ ]*) exit 1;; esac
case "${1-}" in
  deconfig)
    "$bb" ip addr flush dev wlan0
    [ ! -e /run/forge-network-ready ] || "$bb" rm /run/forge-network-ready
    ;;
  bound|renew)
    "$bb" ifconfig wlan0 "$ip" netmask "$subnet" up
    for gateway in $router; do
      "$bb" ip route replace default via "$gateway" dev wlan0
      break
    done
    : > /etc/resolv.conf
    for server in $dns; do printf 'nameserver %s\n' "$server" >> /etc/resolv.conf; done
    chmod 644 /etc/resolv.conf
    if [ -d /os/root/etc ]; then
      "$bb" cp /etc/resolv.conf /os/root/etc/resolv.conf
      chmod 644 /os/root/etc/resolv.conf
    fi
    : > /run/forge-network-ready
    ;;
esac

#!/bin/sh
# Development-only trigger; immediately restore the ordinary hotplug handler.
echo /bin/mdev > /proc/sys/kernel/hotplug
mkdir /run/forge-runtime-trigger.lock 2>/dev/null || exit 0
exec /bin/sh /data/forge-standalone/runtime-probe.sh \
  >/data/forge-standalone/runtime-retry.log 2>&1

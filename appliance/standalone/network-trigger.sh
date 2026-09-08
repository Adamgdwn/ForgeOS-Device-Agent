#!/bin/sh
# One bounded bring-up trigger through Linux's existing kernel hotplug helper.
# The hook is restored before network work starts; no persistent override.
echo /bin/mdev > /proc/sys/kernel/hotplug
mkdir /run/forge-net-trigger.lock 2>/dev/null || exit 0
exec /bin/sh /data/forge-standalone/network-probe.sh \
  >/data/forge-standalone/network-probe.log 2>&1

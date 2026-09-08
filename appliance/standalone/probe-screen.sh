#!/bin/sh
# Keep the direct framebuffer frontend supervised outside PID 1.
/sbin/forge-panel --standalone --socket /run/no-player.sock --music-service \
  --fb /dev/graphics/fb0 --samsung --input /dev/input/event1 \
  >/data/forge/panel-startup.log 2>&1 &
panel=$!
printf '%s\n' "$panel" > /run/forge-panel.pid
wait "$panel"

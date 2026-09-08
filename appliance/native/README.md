# Forge native appliance components

Last Updated: 2026-09-08T17:38:25-06:00

The live SM-T377W interface is the standalone C `forge-panel`, using Samsung's
framebuffer, evdev touch and a private Xvfb browser surface. It runs under Forge
init with no Android framework or Java display host. The existing hardware
kernel is retained. The Android JNI target remains historical source support.

## Components

- `panel.c`: Music, Browse, Home, nonblocking controls and native keyboard.
- `samsung_display.h`, `browser_surface.h`, `touch_state.h`: display access,
  browser-surface input, multitouch slots, dropped-stream recovery and scrolling.
- `music_bridge.c`: allowlisted controls and read-only state through local CDP,
  retaining the browser's active local/Cast playback route.
- `music_bridge_ui_maintenance.h`: recovery of a narrowly matched stalled player
  transition that otherwise intercepts song taps.
- `music_bridge_queue_maintenance.h`: guarded progressive queue rendering with
  canonical data/order preserved, stale-work cancellation and fallback.
- `namespace_run.c`: private Linux browser namespaces and privilege reduction.
- `pcm_sink.c`: native PCM experiments and hardware checks; the browser's local
  audio also uses `linux_service/alsa_compat.c` for the legacy ALSA ABI.
- `core.c`, `engine.c`, `sessiond.c`: original prototype and retained lifecycle
  components; their presence does not mean every binary starts at boot.

## Build

`make -C appliance/native host` builds the host renderer and X11 target when the
local X11 development dependencies are available. The Makefile's `hardware`
target includes panel, bridge and hardware helpers. Override `CC`, `BUILD_DIR`,
`CFLAGS` and `LDFLAGS` for the NDK ARMv7 build.

The proven final bridge uses NDK 27.1's ARMv7 API 21 compiler, strict C11,
`-pthread`, static linking, `-ffunction-sections -fdata-sections` and
`-Wl,--gc-sections`. Section garbage collection is required for the verified
static ARM startup. Output belongs under ignored `output/`, not in source.
The `libforge-panel.so` target and `surface/build-forge-surface.sh` belong to the
superseded Android-backed display and are not current deployment instructions.

## Operation and verification

Browse provides the complete YouTube Music page, native Keyboard and scrolling.
Retry sends F5 and can cause a lengthy reload. Home → Open Dashboard opens the
saved Home Assistant tab. Native Music controls follow the same active Cast
receiver; they do not intentionally start a second local stream.

The installed repairs restored correct song selection and improved measured
changes from about 43 seconds to 14–19 seconds; remaining delay is unresolved.
Tests cover protocol behavior, timeouts without command replay, lifecycle,
recovery, touch and both JavaScript maintenance helpers. Full closeout preflight
passed 246 tests, one skipped and two subtests.

See [standalone operation/recovery](../standalone/README.md) and the
[closeout with evidence and limits](../../docs/research/2026-09-08%20-%20Forge%20Tablet%20Closeout.md).
Keep credentials on-device. Use normal native Cast selection; temporary CDP
receiver overrides previously broke the chooser and must not be repeated.

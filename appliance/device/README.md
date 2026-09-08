# Historical Android appliance lifecycle

Last Updated: 2026-09-08T17:42:41-06:00

This guide describes the superseded Android-backed prototype. The installed
tablet now boots standalone Forge Linux; use the [current operating guide](../standalone/README.md).
Do not apply this historical deployment or rollback sequence to that installation.

In this historical design, Forge’s daily appliance mode keeps Android alive. The original C panel runs from
`libforge-panel.so` through a Java `app_process` host that creates an opaque,
secure 800×1280 RGBA8888 `SurfaceControl`. Android zygote/system_server,
SurfaceFlinger, audioserver, and netd continue running; this avoids the watchdog
and Wi-Fi outages caused by the retired service-stop architecture.

## Daily use

Open **Forge** or press Android Home, then **Start Forge**. The native panel’s
title area opens **Browse**; use **Keyboard** for text and **Retry** (F5) to
reload the displayed page. Browse supports touch, multi-touch slot handling,
dropped-event recovery, and vertical swipes. If its X11 input connection fails,
the panel reconnects it. **Home** → **Open Dashboard** opens the configured Home
Assistant dashboard; this is the correct dashboard entry. **Return to Android**
requires the confirmation tap.

The private browser profile holds the owner’s normal YouTube Music and Home
Assistant sign-ins. Music startup has a one-time blank-only guard after 45
seconds; it does not enter a retry loop or reload an authentication page. Do not
inspect, export, or capture browser authentication material.

Home Assistant’s Brilliant connection was restored by delivering current discovery
inside its NAT guest. A native tablet tap turned the Dining Room light on and a
second tap restored it off, with both states confirmed by Home Assistant. A
persistent discovery service, Forge Brilliant Discovery Relay 0.1.1, now runs
in Home Assistant with boot set to auto; restart and periodic refresh were verified.

YouTube Music may stop playback with its own concurrent-device limit. A later
final check encountered that message despite healthy Wi-Fi. Pause the competing
stream or select the desired output; a Forge restart does not change account
limits. Open Browse to see the provider message. If the other stream has ended
and the message remains, Retry reloads the page; native Play then resumes the
selected music. That sequence restored playback in the final hardware check.

## Installed components and start path

The private install is `/data/local/tmp/forge-native.mdJ5BP`. The Android Home
activity is `org.forge.appliance/.ForgeActivity`; the root broker is
`/system/bin/forge-sessiond`, started by `/system/etc/init/forge-sessiond.rc`.
Its fixed START/STOP/STATUS/HOME protocol authenticates root or the installed
app UID and starts no music or browser automatically.

`forge-session.sh <install> appliance` validates Wi-Fi and required artifacts,
starts the private Linux browser namespace, then invokes:

```sh
CLASSPATH="$install/forge-surface.jar" app_process /system/bin \
  org.forge.surface.ForgeSurface "$install" <music-socket> <xwd> <x11-socket> <home-flag>
```

Because the broker uses `clearenv`, the session script explicitly restores the
trusted fixed ROM ART environment (`ANDROID_ROOT`, `ANDROID_DATA`, runtime and
tzdata roots, plus `BOOTCLASSPATH` and `DEX2OATBOOTCLASSPATH` read from
`/init.environ.rc`). Do not substitute a host or guessed ART classpath.

## Build, deployment, and rollback

Build the Java host with `bash appliance/surface/build-forge-surface.sh`; it
writes `output/forge-surface/forge-surface.jar`. Build the JNI library as the
`libforge-panel.so` Make target from `appliance/native/Makefile`, then deploy
both artifacts to the private install beside `forge-session.sh`, the native
helpers, and `linux-root` with their required modes. The launcher APK build is
`bash appliance/launcher/build-apk.sh`; keep its signing material private.

`forge-session.sh <install> <1..1800>` is the legacy bounded diagnostic
framebuffer mode. It deliberately stops display/framework services and is not
daily appliance mode. STOP for the current SurfaceControl path terminates Forge
but keeps Android services running. Recovery only recreates Android framework
state when a legacy framebuffer takeover or an actually stopped zygote requires
it; never promise a verified full appliance goal from a STOP/recovery result.

Observed hardware evidence includes song-title selection, a light on/off through
native touch, and launcher Start after a reboot. Wi-Fi validation returned at
29.8 seconds during the interruption test while the same Android system_server
and Forge session remained alive. STOP and forced panel-crash recovery each
restored the actual launcher in 6.4 seconds, with validated Wi-Fi. Cast was
verified on an earlier build and has not been retested on this display revision.
Device-specific evidence remains in `docs/research`.

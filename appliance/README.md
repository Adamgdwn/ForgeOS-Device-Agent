# Forge music and home appliance

Last Updated: 2026-09-08T17:38:25-06:00

The Samsung SM-T377W now boots directly into Forge's native green Music, Browse
and Home interface. A custom C init runs Linux networking, direct framebuffer
and touch input, ALSA audio and a private Debian Chromium service. Android's
framework and filesystems have been replaced. The existing device-specific
Linux 3.10.108 kernel and device tree are retained; this is not a new kernel.

YouTube Music runs in the signed-in browser and supports local audio and Cast.
Home Assistant opens in the second browser tab. Correct selected-song playback
is verified, but recent song changes still take roughly 14–19 seconds. Cold
music startup can take two to three minutes on this hardware.

Start with the [standalone operating and recovery guide](standalone/README.md),
[native components](native/README.md), and the
[complete closeout](../docs/research/2026-09-08%20-%20Forge%20Tablet%20Closeout.md).

## Source layout

- `standalone/`: PID 1, boot-image tooling, networking and the completed migration.
- `native/`: panel, touch handling, browser bridge, PCM and process components.
- `linux_service/`: Debian rootfs build and legacy ALSA compatibility.
- `device/`: shared browser supervision plus retained earlier Android session tools.
- `surface/` and `launcher/`: historical Android Java/JNI display and launcher.
- `recovery-policy/`, `verify_ota.py`, `verify_candidate.py` and the device
  contract: retained Android candidate verification, not the installed boot path.

Generated rootfs/images/binaries, account state, credentials and raw device
records are excluded from public Git. Build and recovery need the verified local
hardware inputs described in the operating guide. Do not replay the destructive
migration or old Android deployment instructions on the finished appliance.

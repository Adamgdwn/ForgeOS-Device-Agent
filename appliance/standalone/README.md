# Forge Music and Home

Last Updated: 2026-09-08T17:38:25-06:00

Forge boots this Samsung SM-T377W directly into the green native music and home
interface. Android's SYSTEM, USERDATA and CACHE filesystems were formatted.
The running system uses a custom C init, Linux networking, direct Samsung
framebuffer/touch and ALSA audio, and a private Debian Chromium session for
YouTube Music and Home Assistant. The hardware kernel is the existing Samsung
Linux 3.10.108 kernel with its matching device tree; it is not a newly written
kernel. No Android framework, launcher, Java host, SurfaceFlinger, audio service
or Android networking service starts.

## Using the tablet

- **Select Music** opens the full YouTube Music interface for search, albums,
  playlists and choosing songs. Tap its search field, then **Keyboard** if needed.
- **Music** returns to Forge's native Play/Pause, Next and volume controls.
- **Cast:** choose a song in **Select Music**, wait for it to load, then tap
  YouTube Music's Cast icon at the upper right and choose your speaker.
  **Music** returns to the native controls, which operate that same receiver;
  its name appears on the music card. Kitchen speaker was verified with clear
  owner-confirmed audio, native Pause/Play/volume and Next. The tablet's local
  player pauses during Cast. One fresh touchscreen connection took about eight
  seconds; the final measured Cast Next transition took about twenty-one.
- **Home**, then **Open Dashboard**, opens the saved Home Assistant dashboard.
- Wi-Fi connects automatically. Both sign-ins remain private on the tablet.
- A cold YouTube Music start can take roughly two to three minutes on this CPU.
  The Play control waits until the player is available. After the September 8
  tap/queue repairs, selected song changes measured roughly 14–19 seconds;
  native Next measured 7.8 seconds. Correct selection is verified, but browser
  responsiveness remains a material limitation.
- The permanent boot has no diagnostic countdown. Physical recovery remains
  available. Google account simultaneous-stream limits still apply.

## Storage and services

| Partition | Purpose | Mount |
| --- | --- | --- |
| mmcblk0p10 | Forge boot image, 13,631,488 bytes | initramfs |
| mmcblk0p11 | Preserved TWRP recovery | recovery only |
| mmcblk0p20 | FORGE_OS; Debian runtime in `root/` | `/os` |
| mmcblk0p21 | FORGE_CACHE | recovery only |
| mmcblk0p22 | FORGE_DATA; private configuration and browser state | `/data` |

`/data/forge/state` is bound to `/os/root/var/lib/forge` before the unprivileged
browser namespace starts. Do not inspect or export profile, cookie or Wi-Fi
credential files. The browser runs as UID 65000 without capabilities, with
private mount/PID namespaces and only the necessary audio devices. Its local
control endpoint listens on loopback. USB diagnostics retain physical trust.

The network service keeps both wpa_supplicant and the DHCP renewal client alive.
PID 1 restarts failed network or application supervisors with backoff. The
application supervisor restarts a failed display without stopping the browser
or music. Browser-side music controls can restart independently. Stale control
sockets and Chromium singleton symlinks are cleared only under the exclusive
runtime ownership checks.

## Build and maintenance

Build ARM panel and bridge using `appliance/native/Makefile` and the configured
NDK compiler, with static linking and section garbage collection. Then run:

```sh
bash appliance/standalone/build-probe.sh 900  # timed hardware validation
bash appliance/standalone/build-probe.sh 0    # permanent appliance
```

The build requires the exact verified boot/recovery tools and signed Debian
BusyBox staged in `output/standalone`. Its ELF check rejects the ARM Bionic TLS
alignment failure observed during the first probe. The image repacker preserves
the exact kernel, DTBH, header contract and opaque suffix relative to the device
tree, resizing only final zero padding. Always run source-relative verification
against `boot-verified.img`, then verify the complete partition readback.

`migrate-in-recovery.sh` documents the completed, destructive migration. It is
not a startup script and must not be replayed on the finished appliance.
`verify_tree.c` compares on-device copies without exporting filenames or data.

Useful non-secret diagnostics through the physical USB shell:

```sh
/sbin/forge-admin --shell
cat /data/forge/boot.log
cat /run/forge-panel.status
cat /proc/asound/card0/pcm0p/sub0/status
```

`/sbin/forge-admin --recover` asks PID 1 to shut services down and reboot into
recovery. The USB shell's setuid helper has restricted capabilities; service
startup and networking belong to PID 1. Temporary hotplug diagnostics are for
bring-up only, and the normal hook must remain `/bin/mdev`.

For Cast diagnostics, prefer the ordinary touchscreen chooser and read-only
player state. Do not use temporary CDP `Cast.setSinkToUse` sessions: Chromium
retains their presentation callback after the diagnostic connection closes,
leaving the page's Cast button unresponsive. A fresh music tab clears that
callback; preserve the browser's tab order (music first, Home Assistant second).
`Cast.disable` can terminate routes initiated by its handler and does not reset
that callback. Neither diagnostic method is used by Forge's installed controls.

Exact original BOOT and RECOVERY images remain in `output/standalone` on the
workstation. The preserved recovery is the repair route. Restoring the original
BOOT alone does not recreate Android after its filesystems have been erased.
Current appliance images and hashes, migration counts, playback, touch and
network evidence are under `evidence/tablet-revival/standalone` and
`output/standalone/appliance-manifest.json`.

## Current release record

The [September 8 closeout](../../docs/research/2026-09-08%20-%20Forge%20Tablet%20Closeout.md)
is the current account of the installed bridge repairs, exact hashes, rollback,
receiver-based timing and remaining acceptance work. It supersedes earlier
Android-backed deployment guides. The current bridge survives normal startup;
the final queue-helper revision has not received a fresh reboot/endurance test.
Raw local evidence and firmware backups are not part of the public source tree.

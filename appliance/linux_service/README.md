# ARMv7 Linux browser-service rootfs

`build-armhf-rootfs.sh` creates a small, non-bootable Debian trixie `armhf`
root filesystem for the gteslte Linux test path. It downloads signed packages
only, then extracts their data archives; it does not run maintainer scripts,
emulate ARM, or install/change any host package or APT state.

Run it as a normal user from any directory:

```sh
timeout --signal=TERM --kill-after=30s 12m \
  appliance/linux_service/build-armhf-rootfs.sh
```

Its isolated APT state, downloaded `.deb`s, rootfs, log, version/hash lock,
and artifact are placed under
`~/.local/share/forgeos-tablet-revival/2026-09-06/linux-service` (override
with `FORGEOS_LINUX_SERVICE_OUT`). The package download step is a single APT
stream, capped at five minutes; the invoker supplies the packet’s twelve-minute
overall limit.

The builder bootstraps the two Debian 13 archive keys from `ftp-master` over
HTTPS and refuses them unless their fingerprints match the packet pins. It uses
authenticated trixie and trixie-security `InRelease` indexes and rejects
unauthenticated packages. `package-lock.manifest` records every extracted
package version, size, hash, plus the tarball hash so an exact build can be
audited and repeated against the then-live archive indexes.

Because package maintainer scripts are intentionally not run, the builder
constructs `etc/ssl/certs/ca-certificates.crt` from the extracted Debian
Mozilla CA payload. It does not copy the host trust store.

The actual tablet has now executed this Linux service, rendered the official
YouTube Music player in Chromium150, and delivered real music through its own
speakers with Android audioserver stopped. Adam confirmed clear sound. A small
original ALSA compatibility library supplies the old-kernel SYNC_PTR fallback;
see `alsa_compat.c` and `build-alsa-compat.sh`. Linux Chromium is invoked as the
direct ELF `/usr/lib/chromium/chromium`, avoiding the distribution wrapper's
missing utility assumptions.

The rootfs is used by the [standalone appliance](../standalone/README.md) and
`forge-namespace-run`; it is not a flashable image by itself. The shared browser
supervisor provides Xvfb, UID 65000, ALSA access and local CDP. Forge's custom
init now starts the service without Android, retaining the device kernel.
Earlier Android session launchers remain historical source support. The initial
`.xz` archive exceeded its bounded compression time; the verified transfer used
a separate gzip archive recorded in local device evidence.
Future builder archives use an `.incomplete` temporary name before publication.

Last Updated: 2026-09-08T17:42:41-06:00

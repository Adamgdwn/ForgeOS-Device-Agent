# Recovery debug-policy installer

Last Updated: 2026-09-08T17:42:41-06:00

This installer belongs to the historical Android reference experiment. It is
not required by the installed standalone Forge appliance and must not be run
on its reformatted OS partition. See the [current guide](../standalone/README.md).

Build the deterministic component ZIP from the repository root:

```bash
python3 appliance/recovery-policy/build_recovery_policy_zip.py \
  /home/adamgoodwin/.local/share/forgeos-tablet-revival/2026-09-06/clean-candidate/forgeos-gteslte-debug-policy.zip
```

Run after clean crDroid and MindTheGapps installation, before first system boot.
MindTheGapps unmounts SYSTEM on exit. This component verifies the device,
recovery fstab, SYSTEM by-name mapping to `mmcblk0p20`, and its 6,144,000 sectors;
it rejects an existing SYSTEM mount. It mounts ext4 at its private
`/mnt/forgeos-system`, then validates the mount source, filesystem and write mode.
It requires the exact SHA-256 of `system/build.prop`, applies only the two debug
property changes, preserves uid/gid/mode/SELinux label, atomically replaces the
file, syncs and unmounts. Already-patched content succeeds without rewriting.
Failures return nonzero; an unmount failure must be resolved before reboot.

It never formats or accesses another writable partition. No production
`FORGEOS_TEST_ROOT` or other path override is present. Host tests substitute
fixture paths in a disposable copy and simulate block/mount/SELinux calls while
using real SHA-256 and the complete original property file. The file's inode
changes during atomic replacement; preserved metadata is verified separately.

Source property SHA-256:
`b9af705d7c15b09577725f74a8e694705e0d44a0b5f0a639c8cccc4d3e05b15a`.
Result property SHA-256:
`83af1087bdc8943f1236d2bc057ecc73b0d42e0e411d979d54cad0f8f6f1770a`.

Exact recovery inspection established legacy update-binary execution, runtime
`/sbin/sh` via init's alias to `/system/bin`, and the needed tool binaries.
Physical execution and tool-option compatibility still require the recovery
trial. The locally generated ZIP is unsigned; that recovery exposes an
“Install anyway?” override after signature failure. A host-verified local
component can use that authorized prompt, but only a successful installer exit
and subsequent file/runtime checks prove installation.

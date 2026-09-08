#!/sbin/sh
# Explicitly authorized SM-T377W Android removal. Run only from its recovery.
# Phase one preserves DATA. Phase two requires two verified on-device copies.
set -eu
umask 077
bb=/sbin/busybox
verify=/cache/forge-verify-tree
old=/data/local/tmp/forge-native.mdJ5BP/linux-root
old_base=/data/forge-standalone
[ "$(id -u)" = 0 ]
[ -x /sbin/recovery ] && [ -x /sbin/make_ext4fs ] && [ -x "$verify" ]
[ "$(blockdev --getsize64 /dev/block/mmcblk0p20)" = 3145728000 ]
[ "$(blockdev --getsize64 /dev/block/mmcblk0p22)" = 11358175232 ]
recovery=$(sha256sum /dev/block/mmcblk0p11)
[ "${recovery%% *}" = dfc8ab937098a40e52451aa0159128b1431dc77ff17b8e5197a0f10253dc0cbe ]
case "${1-}" in
  stage)
    [ -x "$old/usr/lib/ld-linux-armhf.so.3" ]
    [ -s "$old_base/wpa_supplicant.conf" ]
    [ ! -e /system/forge-stage/verified ]
    if "$bb" grep -q ' /system ' /proc/mounts; then umount /system; fi
    echo 'Formatting the former Android SYSTEM partition for Forge Linux'
    /sbin/make_ext4fs -l 3145728000 -L FORGE_OS /dev/block/mmcblk0p20 >/cache/forge-format-os.log 2>&1
    mount -t ext4 /dev/block/mmcblk0p20 /system
    mkdir /system/forge-stage
    echo 'Copying Linux runtime locally on the tablet'
    "$bb" cp -a "$old" /system/root >/cache/forge-copy-runtime.log 2>&1
    "$verify" "$old" /system/root
    echo 'Copying private appliance configuration locally on the tablet'
    "$bb" cp -a "$old_base" /system/forge-stage/forge >/cache/forge-copy-config.log 2>&1
    "$verify" "$old_base" /system/forge-stage/forge
    printf 'FORGE_STAGE_V1\n' > /system/forge-stage/verified
    sync
    echo 'SYSTEM is now Forge Linux; DATA is still preserved'
    ;;
  wipe-data)
    [ -r /system/forge-stage/verified ]
    IFS= read -r marker < /system/forge-stage/verified
    [ "$marker" = FORGE_STAGE_V1 ]
    "$verify" "$old" /system/root
    "$verify" "$old_base" /system/forge-stage/forge
    echo 'Verified copies established; formatting old Android USERDATA'
    cd /
    if "$bb" grep -q ' /sdcard ' /proc/mounts; then umount /sdcard; fi
    umount /data
    /sbin/make_ext4fs -l 11358175232 -L FORGE_DATA /dev/block/mmcblk0p22 >/cache/forge-format-data.log 2>&1
    mount -t ext4 /dev/block/mmcblk0p22 /data
    "$bb" cp -a /system/forge-stage/forge /data/forge >/cache/forge-restore-config.log 2>&1
    "$verify" /system/forge-stage/forge /data/forge
    "$bb" cp -a /system/root/var/lib/forge /data/forge/state >/cache/forge-restore-state.log 2>&1
    "$verify" /system/root/var/lib/forge /data/forge/state
    chmod 700 /data/forge
    printf 'FORGE_DATA_V1\n' > /data/forge/migration-complete
    sync
    echo 'Fresh Forge data partition restored; sign-ins remain on this tablet'
    ;;
  *) echo 'Expected stage or wipe-data' >&2; exit 64;;
esac

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
compiler=/home/adamgoodwin/Android/Sdk/ndk/27.1.12297006/toolchains/llvm/prebuilt/linux-x86_64/bin/armv7a-linux-androideabi21-clang
# Match the proven native binaries: dead libc TLS sections must be discarded.
flags=(-Os -std=c11 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -static -Wl,--gc-sections -s)
probe_seconds=${1:-900}
case "$probe_seconds" in 0|900|1800) ;; *) echo 'Use 0 (appliance), 900 or 1800 seconds' >&2; exit 64;; esac
flags+=("-DFORGE_PROBE_SECONDS=$probe_seconds")
"$compiler" "${flags[@]}" appliance/standalone/forge_init.c -o output/standalone/forge-init
"$compiler" "${flags[@]}" appliance/standalone/migrate_wifi.c -o output/standalone/forge-migrate-wifi
python3 appliance/standalone/build_probe.py "$probe_seconds"

#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
ndk=${ANDROID_NDK_HOME:-/home/adamgoodwin/Android/Sdk/ndk/27.1.12297006}
cc="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/armv7a-linux-androideabi21-clang"
out="$repo_dir/output/native-arm/forge-pcm-sink"

if [ ! -x "$cc" ]; then
    echo "missing ARMv7 NDK compiler: $cc" >&2
    exit 127
fi
mkdir -p "$(dirname -- "$out")"
exec "$cc" -Os -std=c11 -Wall -Wextra -Werror -D_POSIX_C_SOURCE=200809L \
    -ffunction-sections -fdata-sections -static -Wl,--gc-sections -Wl,--build-id=none -s \
    "$repo_dir/appliance/native/pcm_sink.c" -o "$out"

#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cc=/home/adamgoodwin/Android/Sdk/ndk/27.1.12297006/toolchains/llvm/prebuilt/linux-x86_64/bin/clang
out="$repo_dir/output/native-arm/forge-alsa-compat.so"

if [ ! -x "$cc" ]; then
    echo "missing ARM NDK compiler: $cc" >&2
    exit 127
fi
mkdir -p "$(dirname -- "$out")"
exec "$cc" --target=armv7-linux-gnueabihf -mfloat-abi=hard -Os -fPIC -shared \
    -nostdlib -fuse-ld=lld -std=c11 -Wall -Wextra -Werror \
    "$repo_dir/appliance/linux_service/alsa_compat.c" -o "$out"

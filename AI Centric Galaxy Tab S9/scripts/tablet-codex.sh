#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
# The official static ARM64 client needs Linux's resolver path. PRoot maps
# that one file; this is compatibility plumbing, not a security sandbox.
tablet_prefix=/data/data/com.termux/files/usr
tablet_home=/data/data/com.termux/files/home
export TMPDIR="$tablet_prefix/tmp"
export PATH="$tablet_home/galaxy-codex/codex-path:$tablet_home/galaxy-codex/codex-resources:$tablet_prefix/bin:/system/bin"
exec /system/bin/env -u LD_PRELOAD \
  SSL_CERT_FILE="$tablet_prefix/etc/tls/cert.pem" \
  "$tablet_prefix/bin/proot" -b "$tablet_prefix/etc/resolv.conf:/etc/resolv.conf" \
  "$tablet_home/galaxy-codex/bin/codex" "$@"

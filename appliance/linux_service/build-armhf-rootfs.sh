#!/usr/bin/env bash
# Build a minimal, extraction-only Debian trixie armhf browser service rootfs.
# It never installs packages or changes APT state on the host.
set -euo pipefail

readonly BUILD_ID="2026-09-06"
readonly OUT_BASE="${FORGEOS_LINUX_SERVICE_OUT:-$HOME/.local/share/forgeos-tablet-revival/$BUILD_ID/linux-service}"
readonly WORK="$OUT_BASE/work"
readonly ROOTFS="$OUT_BASE/rootfs"
readonly ARCHIVE="$OUT_BASE/forgeos-gteslte-browser-service-trixie-armhf.tar.xz"
readonly LOG="$OUT_BASE/build.log"
readonly KEY_MAIN_FPR="04B54C3CDCA79751B16BC6B5225629DF75B188BD"
readonly KEY_SECURITY_FPR="5E04A1E3223A19A20706E20F9904613D4CCE68C6"
readonly REQUIRED_PKGS=(chromium xvfb alsa-utils ca-certificates fonts-dejavu-core dash coreutils libc-bin)

die() { echo "ERROR: $*" >&2; exit 1; }
stage() { printf '%s stage=%s\n' "$(date -Iseconds)" "$1" | tee -a "$LOG"; }
run_limited() { timeout --signal=TERM --kill-after=30s 5m "$@"; }

[[ "$(id -u)" != 0 ]] || die "Run as an unprivileged user; this builder needs no root."
for tool in apt-get curl dpkg-deb gpg sha256sum tar timeout; do command -v "$tool" >/dev/null || die "missing host tool: $tool"; done
mkdir -p "$OUT_BASE" "$WORK" "$ROOTFS"
: > "$LOG"

stage bootstrap-isolated-apt
rm -rf "$WORK/apt" "$WORK/keys" "$ROOTFS"
mkdir -p "$WORK/apt/lists/partial" "$WORK/apt/archives/partial" "$WORK/apt/etc" "$WORK/apt/empty-sourceparts" "$WORK/apt/empty-trustedparts" "$WORK/keys" "$ROOTFS"
: > "$WORK/apt/status"
cat > "$WORK/apt/etc/sources.list" <<EOF
deb [signed-by=$WORK/apt/etc/trusted.gpg] https://deb.debian.org/debian trixie main
deb [signed-by=$WORK/apt/etc/trusted.gpg] https://security.debian.org/debian-security trixie-security main
EOF

stage fetch-and-pin-debian-keys
curl --fail --silent --show-error --location --proto '=https' \
  https://ftp-master.debian.org/keys/archive-key-13.asc -o "$WORK/keys/main.asc"
curl --fail --silent --show-error --location --proto '=https' \
  https://ftp-master.debian.org/keys/archive-key-13-security.asc -o "$WORK/keys/security.asc"
verify_key() {
  local file="$1" expected="$2" actual
  actual="$(gpg --show-keys --with-colons "$file" | awk -F: '$1 == "fpr" { print $10; exit }')"
  [[ "$actual" == "$expected" ]] || die "unexpected signing key in $file: $actual"
}
verify_key "$WORK/keys/main.asc" "$KEY_MAIN_FPR"
verify_key "$WORK/keys/security.asc" "$KEY_SECURITY_FPR"
gpg --batch --yes --dearmor --output "$WORK/keys/main.gpg" "$WORK/keys/main.asc"
gpg --batch --yes --dearmor --output "$WORK/keys/security.gpg" "$WORK/keys/security.asc"
cat "$WORK/keys/main.gpg" "$WORK/keys/security.gpg" > "$WORK/apt/etc/trusted.gpg"

APT=(apt-get
  -o Dir="$WORK/apt"
  -o Dir::Etc::sourcelist="$WORK/apt/etc/sources.list"
  -o Dir::Etc::sourceparts="$WORK/apt/empty-sourceparts"
  -o Dir::State::status="$WORK/apt/status"
  -o Dir::State::lists="$WORK/apt/lists"
  -o Dir::Cache::archives="$WORK/apt/archives"
  -o APT::Architecture=armhf
  -o Acquire::Languages=none
  -o Acquire::AllowInsecureRepositories=false
  -o APT::Get::AllowUnauthenticated=false)

stage signed-index-update
run_limited "${APT[@]}" update
stage resolve-and-download-armhf-packages
run_limited "${APT[@]}" --download-only --yes --no-install-recommends install "${REQUIRED_PKGS[@]}"

stage record-version-lock
{
  echo "build_id=$BUILD_ID"
  echo "architecture=armhf"
  echo "generated_at=$(date -Iseconds)"
  echo "keys=$KEY_MAIN_FPR,$KEY_SECURITY_FPR"
  echo "sources=debian:trixie,security:trixie-security"
  echo "requested_packages=${REQUIRED_PKGS[*]}"
  for deb in "$WORK/apt/archives"/*.deb; do
    [[ -e "$deb" ]] || die "APT resolved no Debian packages"
    printf 'package=%s version=%s architecture=%s size=%s sha256=%s file=%s\n' \
      "$(dpkg-deb -f "$deb" Package)" "$(dpkg-deb -f "$deb" Version)" \
      "$(dpkg-deb -f "$deb" Architecture)" "$(stat -c '%s' "$deb")" \
      "$(sha256sum "$deb" | awk '{print $1}')" "$(basename "$deb")"
  done | sort
} > "$OUT_BASE/package-lock.manifest"

stage extract-rootfs-without-maintainer-scripts
for deb in "$WORK/apt/archives"/*.deb; do dpkg-deb -x "$deb" "$ROOTFS"; done
mkdir -p "$ROOTFS"/{dev,proc,sys,tmp,run,etc,usr/local/bin}
chmod 1777 "$ROOTFS/tmp"
mkdir -p "$ROOTFS/etc/ssl/certs"
# Maintainer scripts cannot run during host-side extraction.  Build the PEM
# bundle from the just-extracted Debian CA payload instead of borrowing host CAs.
find "$ROOTFS/usr/share/ca-certificates/mozilla" -type f -name '*.crt' -print0 \
  | sort -z | xargs -0 cat > "$ROOTFS/etc/ssl/certs/ca-certificates.crt"
[[ -s "$ROOTFS/etc/ssl/certs/ca-certificates.crt" ]] || die "Debian CA bundle is empty"
cat > "$ROOTFS/etc/hosts" <<'EOF'
127.0.0.1 localhost
EOF
cat > "$ROOTFS/usr/local/bin/forge-browser-service" <<'EOF'
#!/bin/sh
set -eu
export DISPLAY="${DISPLAY:-:0}"
export HOME="${HOME:-/tmp/forge-browser}"
mkdir -p "$HOME"
Xvfb "$DISPLAY" -screen 0 "${FORGEOS_SCREEN:-1280x800x24}" -nolisten tcp -nolisten local &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT INT TERM
# The distro wrapper assumes utilities that extraction-only closure omits.
/usr/lib/chromium/chromium --no-first-run --disable-background-networking --disable-component-update "$@"
EOF
chmod 0755 "$ROOTFS/usr/local/bin/forge-browser-service"

stage archive-rootfs
# A timeout must not truncate the last complete, hash-recorded artifact.
tar --numeric-owner --owner=0 --group=0 -C "$ROOTFS" -cJf "$ARCHIVE.incomplete" .
mv -f "$ARCHIVE.incomplete" "$ARCHIVE"
archive_sha="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
printf 'rootfs_archive=%s\nrootfs_archive_sha256=%s\nrootfs_bytes=%s\n' \
  "$(basename "$ARCHIVE")" "$archive_sha" "$(stat -c '%s' "$ARCHIVE")" >> "$OUT_BASE/package-lock.manifest"
stage complete
echo "Artifact: $ARCHIVE" | tee -a "$LOG"
echo "SHA256: $archive_sha" | tee -a "$LOG"

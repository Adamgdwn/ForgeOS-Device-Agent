#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
sdk_dir=${ANDROID_SDK_ROOT:-/home/adamgoodwin/Android/Sdk}
tools_dir="$sdk_dir/build-tools/35.0.0"
android_jar="$sdk_dir/platforms/android-35/android.jar"
out_dir="$root_dir/output/launcher"
work_dir="$out_dir/work"
keystore="$out_dir/forge-local-test.keystore"
password_file="$out_dir/.keystore-pass"
apk="$out_dir/forge-launcher.apk"

for tool in "$tools_dir/aapt2" "$tools_dir/d8" "$tools_dir/apksigner" "$tools_dir/zipalign" javac keytool; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Missing build tool: $tool" >&2; exit 1; }
done
[[ -r "$android_jar" ]] || { echo "Missing Android platform jar: $android_jar" >&2; exit 1; }
umask 077
rm -rf "$work_dir"
mkdir -p "$work_dir/classes" "$work_dir/res" "$out_dir"
"$tools_dir/aapt2" compile --dir "$root_dir/appliance/launcher/res" -o "$work_dir/res.zip"
"$tools_dir/aapt2" link -I "$android_jar" --manifest "$root_dir/appliance/launcher/AndroidManifest.xml" --min-sdk-version 21 --target-sdk-version 29 --auto-add-overlay -o "$work_dir/unsigned-unaligned.apk" "$work_dir/res.zip"
mapfile -t sources < <(find "$root_dir/appliance/launcher/src" -name '*.java' -print)
javac -source 8 -target 8 -Xlint:all,-options -Werror -classpath "$android_jar" -d "$work_dir/classes" "${sources[@]}"
mkdir -p "$work_dir/dex"
mapfile -t class_files < <(find "$work_dir/classes" -name '*.class' -print)
"$tools_dir/d8" --min-api 21 --lib "$android_jar" --output "$work_dir/dex" "${class_files[@]}"
(cd "$work_dir/dex" && zip -q "$work_dir/unsigned-unaligned.apk" classes.dex)
"$tools_dir/zipalign" -f 4 "$work_dir/unsigned-unaligned.apk" "$work_dir/unsigned.apk"
if [[ ! -f "$keystore" ]]; then
  key_pass=$(head -c 32 /dev/urandom | base64 | tr -d '\n')
  printf '%s\n%s\n' "$key_pass" "$key_pass" > "$password_file"
  chmod 600 "$password_file"
  KEY_PASS=$(head -n 1 "$password_file") keytool -genkeypair -keystore "$keystore" -storetype PKCS12 -alias forge-local -dname 'CN=Forge Local Test' -keyalg RSA -keysize 2048 -validity 3650 -storepass:env KEY_PASS -keypass:env KEY_PASS -noprompt
  chmod 600 "$keystore"
fi
[[ -f "$password_file" ]] || { echo "Missing local keystore password file" >&2; exit 1; }
if [[ $(wc -l < "$password_file") -lt 2 ]]; then
  key_pass=$(head -n 1 "$password_file")
  printf '%s\n%s\n' "$key_pass" "$key_pass" > "$password_file"
  chmod 600 "$password_file"
fi
"$tools_dir/apksigner" sign --ks "$keystore" --ks-key-alias forge-local --ks-pass "file:$password_file" --key-pass "file:$password_file" --out "$apk" "$work_dir/unsigned.apk"
"$tools_dir/apksigner" verify --verbose "$apk"
echo "Built $apk"

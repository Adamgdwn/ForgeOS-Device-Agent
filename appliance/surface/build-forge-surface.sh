#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
sdk_dir=${ANDROID_SDK_ROOT:-/home/adamgoodwin/Android/Sdk}
tools_dir="$sdk_dir/build-tools/35.0.0"
android_jar="$sdk_dir/platforms/android-35/android.jar"
out_dir="$root_dir/output/forge-surface"
work_dir="$out_dir/work"
jar_file="$out_dir/forge-surface.jar"

for tool in javac jar "$tools_dir/d8"; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Missing build tool: $tool" >&2
        exit 1
    }
done
[[ -r "$android_jar" ]] || {
    echo "Missing Android platform jar: $android_jar" >&2
    exit 1
}

rm -rf "$work_dir"
mkdir -p "$work_dir/classes" "$work_dir/dex" "$out_dir"
mapfile -t sources < <(find "$root_dir/appliance/surface/src" -name '*.java' -print | LC_ALL=C sort)
(( ${#sources[@]} > 0 )) || { echo "No Java sources found" >&2; exit 1; }

javac -source 8 -target 8 -Xlint:all,-options -Werror -classpath "$android_jar" \
    -d "$work_dir/classes" "${sources[@]}"
mapfile -t class_files < <(find "$work_dir/classes" -name '*.class' -print | LC_ALL=C sort)
"$tools_dir/d8" --min-api 29 --lib "$android_jar" --output "$work_dir/dex" "${class_files[@]}"
jar --create --file "$jar_file" --date=1980-01-01T00:00:02Z -C "$work_dir/dex" classes.dex
echo "Built $jar_file"

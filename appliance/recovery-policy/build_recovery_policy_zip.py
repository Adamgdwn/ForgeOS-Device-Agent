#!/usr/bin/env python3
"""Create the recovery policy ZIP with stable names, timestamps, and modes."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
MEMBERS = (
    Path("META-INF/com/google/android/updater-script"),
    Path("META-INF/com/google/android/update-binary"),
)


def write_member(archive: zipfile.ZipFile, relative: Path) -> None:
    info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ((0o755 if relative.name == "update-binary" else 0o644) & 0xFFFF) << 16
    archive.writestr(info, (ROOT / relative).read_bytes(), compresslevel=9)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", strict_timestamps=True) as archive:
        for member in MEMBERS:
            write_member(archive, member)


if __name__ == "__main__":
    main()

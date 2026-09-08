#!/usr/bin/env python3
"""Conservative repacker for the gteslte legacy Android boot image.

This is an offline host tool.  It deliberately accepts only the legacy layout
observed in the preserved gteslte image; it never writes a block device.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import struct
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"ANDROID!"
DTBH = b"DTBH"
HEADER_MIN = 608
MAX_IMAGE = 13 * 1024 * 1024
MAX_CPIO_ENTRIES = 4096
MAX_CPIO_BYTES = 64 * 1024 * 1024


class BootImageError(ValueError):
    pass


def _align(value: int, page: int) -> int:
    return (value + page - 1) // page * page


def _range(data: bytes, start: int, length: int, label: str) -> bytes:
    if start < 0 or length < 0 or start + length > len(data):
        raise BootImageError(f"truncated {label}")
    return data[start : start + length]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


@dataclass(frozen=True)
class BootImage:
    raw: bytes
    page_size: int
    kernel_size: int
    ramdisk_size: int
    second_size: int
    dt_size: int
    fields: tuple[int, ...]
    kernel_offset: int
    ramdisk_offset: int
    second_offset: int
    dt_offset: int
    tail_offset: int
    id_mode: str

    @property
    def kernel(self) -> bytes:
        return _range(self.raw, self.kernel_offset, self.kernel_size, "kernel")

    @property
    def ramdisk(self) -> bytes:
        return _range(self.raw, self.ramdisk_offset, self.ramdisk_size, "ramdisk")

    @property
    def second(self) -> bytes:
        return _range(self.raw, self.second_offset, self.second_size, "second stage")

    @property
    def dt(self) -> bytes:
        return _range(self.raw, self.dt_offset, self.dt_size, "DTBH")

    @property
    def tail(self) -> bytes:
        return self.raw[self.tail_offset :]


def _boot_id(kernel: bytes, ramdisk: bytes, second: bytes, dt: bytes, mode: str) -> bytes:
    digest = hashlib.sha1()
    for payload in (kernel, ramdisk, second):
        digest.update(payload)
        digest.update(struct.pack("<I", len(payload)))
    if mode == "dt-size":
        digest.update(dt)
        digest.update(struct.pack("<I", len(dt)))
    elif mode != "no-dt":
        raise BootImageError(f"unknown legacy ID convention {mode}")
    return digest.digest()


def validate_gzip_newc(ramdisk: bytes) -> None:
    if not ramdisk.startswith(b"\x1f\x8b"):
        raise BootImageError("ramdisk is not gzip")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(ramdisk)) as stream:
            archive = stream.read(MAX_CPIO_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise BootImageError("ramdisk gzip is invalid") from exc
    if len(archive) > MAX_CPIO_BYTES:
        raise BootImageError("cpio archive exceeds expanded limit")
    pos = entries = 0
    names = set()
    init_executable = False
    while True:
        if entries >= MAX_CPIO_ENTRIES:
            raise BootImageError("cpio entry limit exceeded")
        header = _range(archive, pos, 110, "cpio header")
        if header[:6] not in (b"070701", b"070702"):
            raise BootImageError("cpio is not newc/crc")
        try:
            values = [int(header[6 + i * 8 : 14 + i * 8], 16) for i in range(13)]
        except ValueError as exc:
            raise BootImageError("non-hex cpio header") from exc
        mode, size, name_size = values[1], values[6], values[11]
        if not 1 <= name_size <= 4096:
            raise BootImageError("invalid cpio name length")
        name_raw = _range(archive, pos + 110, name_size, "cpio name")
        if name_raw[-1:] != b"\0":
            raise BootImageError("unterminated cpio name")
        name = name_raw[:-1].decode("utf-8", "surrogateescape")
        if '\0' in name or name in names or name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/")):
            raise BootImageError("unsafe cpio path")
        names.add(name)
        data_start = _align(pos + 110 + name_size, 4)
        _range(archive, data_start, size, "cpio payload")
        pos = _align(data_start + size, 4)
        entries += 1
        if name == "TRAILER!!!":
            if size != 0 or any(archive[pos:]):
                raise BootImageError("invalid cpio trailer")
            break
        if name == "init" and (mode & 0o170000) == 0o100000 and (mode & 0o111):
            init_executable = True
    if not init_executable:
        raise BootImageError("cpio has no executable /init")


def _validate_dt(dt: bytes) -> None:
    if len(dt) < 16 or dt[:4] != DTBH or _u32(dt, 4) != 2:
        raise BootImageError("unsupported Samsung DTBH")
    count = _u32(dt, 8)
    if not 1 <= count <= 64 or 16 + count * 32 > len(dt):
        raise BootImageError("invalid DTBH table")
    greatest_end = 0
    for index in range(count):
        # Samsung DTBH v2 entries start with board/revision metadata; the
        # (container-relative) DTB offset and size are the final fields.
        offset = _u32(dt, 32 + index * 32)
        size = _u32(dt, 36 + index * 32)
        if size < 8 or offset < 16 + count * 32 or offset + size > len(dt):
            raise BootImageError("DTBH entry outside container")
        if _range(dt, offset, 4, "DTB magic") != b"\xd0\x0d\xfe\xed":
            raise BootImageError("DTBH entry is not an FDT")
        greatest_end = max(greatest_end, offset + size)
    if greatest_end != len(dt):
        raise BootImageError("DTBH has unaccounted content")


def parse_image(raw: bytes) -> BootImage:
    if len(raw) > MAX_IMAGE:
        raise BootImageError("image exceeds 13 MiB limit")
    if len(raw) < HEADER_MIN or raw[:8] != MAGIC:
        raise BootImageError("not a legacy Android boot image")
    fields = struct.unpack_from("<10I", raw, 8)
    kernel_size, _, ramdisk_size, _, second_size, _, _, page_size, dt_size, _ = fields
    if page_size not in (2048, 4096) or page_size < HEADER_MIN:
        raise BootImageError("unsupported page size")
    kernel_offset = page_size
    ramdisk_offset = kernel_offset + _align(kernel_size, page_size)
    second_offset = ramdisk_offset + _align(ramdisk_size, page_size)
    dt_offset = second_offset + _align(second_size, page_size)
    tail_offset = dt_offset + _align(dt_size, page_size)
    for offset, size, name in ((kernel_offset, kernel_size, "kernel"), (ramdisk_offset, ramdisk_size, "ramdisk"), (second_offset, second_size, "second"), (dt_offset, dt_size, "dt")):
        _range(raw, offset, size, name)
    if tail_offset > len(raw):
        raise BootImageError("truncated component padding")
    for offset, size, name in ((kernel_offset, kernel_size, "kernel"), (ramdisk_offset, ramdisk_size, "ramdisk"), (second_offset, second_size, "second"), (dt_offset, dt_size, "dt")):
        if any(raw[offset + size : offset + _align(size, page_size)]):
            raise BootImageError(f"nonzero {name} padding")
    kernel = _range(raw, kernel_offset, kernel_size, "kernel")
    if len(kernel) < 0x28 or kernel[0x24:0x28] != b"\x18\x28\x6f\x01":
        raise BootImageError("kernel lacks ARM zImage magic")
    ramdisk = _range(raw, ramdisk_offset, ramdisk_size, "ramdisk")
    validate_gzip_newc(ramdisk)
    dt = _range(raw, dt_offset, dt_size, "dt")
    _validate_dt(dt)
    stored = raw[576:596]
    modes = [mode for mode in ("dt-size", "no-dt") if _boot_id(kernel, ramdisk, _range(raw, second_offset, second_size, "second"), dt, mode) == stored]
    if len(modes) != 1 or any(raw[596:608]):
        raise BootImageError("unproven legacy boot ID convention")
    return BootImage(raw, page_size, kernel_size, ramdisk_size, second_size, dt_size, fields, kernel_offset, ramdisk_offset, second_offset, dt_offset, tail_offset, modes[0])


def manifest(image: BootImage) -> dict[str, object]:
    return {"image_sha256": hashlib.sha256(image.raw).hexdigest(), "size": len(image.raw), "page_size": image.page_size, "id_convention": image.id_mode, "offsets": {"kernel": image.kernel_offset, "ramdisk": image.ramdisk_offset, "second": image.second_offset, "dtbh": image.dt_offset, "tail": image.tail_offset}, "sizes": {"kernel": image.kernel_size, "ramdisk": image.ramdisk_size, "second": image.second_size, "dtbh": image.dt_size}, "hashes": {"kernel": hashlib.sha256(image.kernel).hexdigest(), "ramdisk": hashlib.sha256(image.ramdisk).hexdigest(), "second": hashlib.sha256(image.second).hexdigest(), "dtbh": hashlib.sha256(image.dt).hexdigest(), "tail": hashlib.sha256(image.tail).hexdigest()}}


def repack(source: bytes, ramdisk: bytes) -> bytes:
    base = parse_image(source)
    validate_gzip_newc(ramdisk)
    header = bytearray(source[: base.page_size])
    struct.pack_into("<I", header, 16, len(ramdisk))
    ident = _boot_id(base.kernel, ramdisk, base.second, base.dt, base.id_mode)
    header[576:608] = ident + b"\0" * 12
    result = bytes(header) + base.kernel + b"\0" * (_align(base.kernel_size, base.page_size) - base.kernel_size)
    result += ramdisk + b"\0" * (_align(len(ramdisk), base.page_size) - len(ramdisk))
    result += base.second + b"\0" * (_align(base.second_size, base.page_size) - base.second_size)
    result += base.dt + b"\0" * (_align(base.dt_size, base.page_size) - base.dt_size)
    # The full partition contains older nonzero bytes after the active image.
    # Preserve that opaque suffix at the same component-relative position;
    # only the trailing all-zero partition padding may shrink or grow.
    result += base.tail.rstrip(b"\0")
    if len(result) > MAX_IMAGE:
        raise BootImageError("repacked image exceeds 13 MiB limit")
    # Partition padding has no payload. Resize it when the ramdisk grows.
    result += b"\0" * max(0, len(source) - len(result))
    candidate = parse_image(result)
    if candidate.kernel != base.kernel or candidate.dt != base.dt or candidate.second != base.second or candidate.tail.rstrip(b"\0") != base.tail.rstrip(b"\0"):
        raise BootImageError("repack changed preserved payload")
    return result


def verify_against(source: bytes, candidate: bytes) -> BootImage:
    """Require a candidate to preserve every source-only opaque payload."""
    base, checked = parse_image(source), parse_image(candidate)
    if base.raw[8:16] != checked.raw[8:16] or base.raw[20:576] != checked.raw[20:576] or base.raw[608:base.page_size] != checked.raw[608:checked.page_size]:
        raise BootImageError("candidate changed preserved header fields")
    if base.kernel != checked.kernel or base.second != checked.second or base.dt != checked.dt or base.tail.rstrip(b"\0") != checked.tail.rstrip(b"\0"):
        raise BootImageError("candidate changed preserved payload or opaque tail")
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify"); verify.add_argument("image", type=Path); verify.add_argument("--source", type=Path)
    build = sub.add_parser("repack"); build.add_argument("source", type=Path); build.add_argument("ramdisk", type=Path); build.add_argument("output", type=Path); build.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        raw = args.image.read_bytes()
        image = verify_against(args.source.read_bytes(), raw) if args.source else parse_image(raw)
        print(json.dumps(manifest(image), sort_keys=True))
        return 0
    output = repack(args.source.read_bytes(), args.ramdisk.read_bytes())
    args.output.write_bytes(output)
    parsed = parse_image(output)
    target = args.manifest or args.output.with_suffix(args.output.suffix + ".manifest.json")
    target.write_text(json.dumps(manifest(parsed), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BootImageError as exc:
        raise SystemExit(f"error: {exc}")

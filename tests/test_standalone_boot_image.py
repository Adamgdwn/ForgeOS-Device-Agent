import gzip
import hashlib
import random
import struct
from pathlib import Path

import pytest

from appliance.standalone.boot_image import BootImageError, parse_image, repack, validate_gzip_newc, verify_against


SOURCE = Path("output/standalone/boot-before-forge.img")


def test_real_image_roundtrip_when_present() -> None:
    if not SOURCE.exists():
        pytest.skip("preserved gteslte image not available")
    source = SOURCE.read_bytes()
    image = parse_image(source)
    assert repack(source, image.ramdisk) == source


def test_real_image_detects_header_corruption_when_present() -> None:
    if not SOURCE.exists():
        pytest.skip("preserved gteslte image not available")
    raw = bytearray(SOURCE.read_bytes())
    raw[0] = 0
    with pytest.raises(BootImageError, match="legacy Android"):
        parse_image(bytes(raw))


def test_real_image_rejects_tail_corruption_and_component_truncation_when_present() -> None:
    if not SOURCE.exists():
        pytest.skip("preserved gteslte image not available")
    raw = SOURCE.read_bytes()
    image = parse_image(raw)
    altered = bytearray(raw)
    altered[-1] = 1
    with pytest.raises(BootImageError, match="opaque tail"):
        verify_against(raw, bytes(altered))
    with pytest.raises(BootImageError, match="truncated dt"):
        parse_image(raw[: image.dt_offset + 64])


def test_cpio_rejects_truncated_gzip() -> None:
    with pytest.raises(BootImageError, match="gzip"):
        validate_gzip_newc(gzip.compress(b"070701")[:-2])


def test_cpio_rejects_non_gzip() -> None:
    with pytest.raises(BootImageError, match="not gzip"):
        validate_gzip_newc(b"not a ramdisk")


def test_larger_valid_ramdisk_uses_partition_padding():
    if not SOURCE.exists():
        pytest.skip("preserved gteslte image not available")
    source = SOURCE.read_bytes()
    image = parse_image(source)
    # Incompressible file data creates a valid larger executable init archive.
    data = random.Random(42).randbytes(1_500_000)
    def entry(name, payload, mode):
        name = name.encode() + b'\0'
        fields = [1, mode, 0, 0, 1, 0, len(payload), 0, 0, 0, 0, len(name), 0]
        result = b'070701' + ''.join(f'{v:08x}' for v in fields).encode() + name
        result += b'\0' * (-len(result) % 4)
        result += payload
        return result + b'\0' * (-len(result) % 4)
    ramdisk = gzip.compress(entry('init', data, 0o100755) + entry('TRAILER!!!', b'', 0))
    assert len(ramdisk) > image.ramdisk_size
    candidate = repack(source, ramdisk)
    assert len(candidate) == len(source)
    assert verify_against(source, candidate).ramdisk == ramdisk


def test_rejects_appended_dd_diagnostics():
    if not SOURCE.exists():
        pytest.skip("preserved gteslte image not available")
    with pytest.raises(BootImageError, match='13 MiB'):
        parse_image(SOURCE.read_bytes() + b'13+0 records in\n')

import struct

import pytest

from appliance.standalone.build_probe import check_init_elf


def elf(kind=7, align=8):
    data = bytearray(128)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<HH', data, 16, 2, 40)
    struct.pack_into('<I', data, 28, 52)
    struct.pack_into('<HH', data, 42, 32, 1)
    struct.pack_into('<8I', data, 52, kind, 96, 96, 96, 8, 8, 4, align)
    return bytes(data)


def test_init_rejects_the_observed_pre_main_tls_abort():
    with pytest.raises(ValueError, match='32-byte'):
        check_init_elf(elf())


def test_init_accepts_aligned_tls_and_no_tls():
    check_init_elf(elf(align=32))
    check_init_elf(elf(kind=1))


def test_init_rejects_dynamic_or_truncated_image():
    with pytest.raises(ValueError, match='interpreter'):
        check_init_elf(elf(kind=3))
    with pytest.raises(ValueError, match='headers'):
        check_init_elf(elf()[:60])

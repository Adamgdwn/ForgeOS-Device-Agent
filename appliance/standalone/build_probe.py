#!/usr/bin/env python3
"""Assemble the fixed Forge PID-1 hardware probe; no device writes."""
from pathlib import Path
import gzip
import hashlib
import json
import stat
import struct
import sys

try:
    from .boot_image import repack, verify_against, manifest
except ImportError:
    from boot_image import repack, verify_against, manifest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/standalone'


def check_init_elf(data):
    if len(data) < 52 or data[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('init must be a little-endian ELF32 executable')
    if struct.unpack_from('<HH', data, 16) != (2, 40):
        raise ValueError('init must be a static ARM executable')
    start = struct.unpack_from('<I', data, 28)[0]
    size, count = struct.unpack_from('<HH', data, 42)
    if size != 32 or not count or start + size * count > len(data):
        raise ValueError('init program headers are invalid')
    for index in range(count):
        kind, offset, address, _, filesz, memsz, _, align = struct.unpack_from('<8I', data, start + index * size)
        if kind == 3:
            raise ValueError('init must not depend on a dynamic interpreter')
        if kind == 7 and memsz and (align < 32 or align & (align - 1) or address % align != offset % align):
            raise ValueError('init TLS does not meet the ARM Bionic 32-byte alignment contract')


def archive(entries):
    result = bytearray()
    for number, (name, mode, data) in enumerate(entries + [('TRAILER!!!', 0, b'')], 1):
        encoded = name.encode() + b'\0'
        fields = [number, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
        if name == 'dev/kmsg':
            fields[9:11] = [1, 11]
        result += b'070701' + ''.join(f'{x:08x}' for x in fields).encode() + encoded
        result += b'\0' * (-len(result) % 4)
        result += data
        result += b'\0' * (-len(result) % 4)
    return gzip.compress(result, compresslevel=6, mtime=0)


def main():
    check_init_elf((OUT / 'forge-init').read_bytes())
    entries = [(p, stat.S_IFDIR | 0o755, b'') for p in
               ['bin', 'sbin', 'etc', 'etc/forge', 'dev', 'proc', 'sys', 'run', 'tmp', 'data', 'os']]
    entries.append(('dev/kmsg', stat.S_IFCHR | 0o600, b''))
    for path, source, mode in [
        ('init', OUT / 'forge-init', 0o755),
        ('sbin/forge-admin', OUT / 'forge-init', 0o4755),
        ('sbin/adbd', OUT / 'recovery-tools/adbd', 0o755),
        ('sbin/forge-panel', ROOT / 'output/native-arm/forge-panel', 0o755),
        ('sbin/forge-namespace-run', ROOT / 'output/native-arm/forge-namespace-run', 0o755),
        ('bin/busybox', OUT / 'network-root/usr/bin/busybox', 0o755),
        ('etc/forge/probe-screen.sh', ROOT / 'appliance/standalone/probe-screen.sh', 0o755),
    ]:
        entries.append((path, stat.S_IFREG | mode, source.read_bytes()))
    for name in ['network-service.sh', 'runtime.sh', 'audio-route.sh', 'dhcp-event.sh']:
        entries.append(('etc/forge/' + name, stat.S_IFREG | 0o755,
                        (ROOT / 'appliance/standalone' / name).read_bytes()))
    for name in ['sh', 'cat', 'ls', 'echo', 'mdev', 'mount', 'umount', 'ps', 'ip',
                 'dd', 'chmod', 'mkdir', 'sleep', 'dmesg', 'sha256sum', 'reboot', 'sync']:
        entries.append(('bin/' + name, stat.S_IFLNK | 0o777, b'/bin/busybox'))
    entries.append(('sbin/sh', stat.S_IFLNK | 0o777, b'/bin/busybox'))
    ramdisk = archive(entries)
    (OUT / 'probe-ramdisk.cpio.gz').write_bytes(ramdisk)
    source = (OUT / 'boot-verified.img').read_bytes()
    candidate = repack(source, ramdisk)
    checked = verify_against(source, candidate)
    (OUT / 'forge-probe.img').write_bytes(candidate)
    evidence = manifest(checked)
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 900
    evidence['scope'] = f'{seconds}-second independent PID-1 probe' if seconds else 'Standalone Forge appliance'
    evidence['files'] = {p: hashlib.sha256(d).hexdigest() for p, m, d in entries if stat.S_ISREG(m)}
    (OUT / 'probe-manifest.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


if __name__ == '__main__':
    main()

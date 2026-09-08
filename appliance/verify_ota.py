#!/usr/bin/env python3
"""Check an Android whole-file OTA signature against a pinned certificate.

Read-only host utility; does not install anything. Container bounds follow:
https://android.googlesource.com/platform/bootable/recovery/+/refs/heads/android10-release/install/verifier.cpp
OpenSSL verifies the detached CMS signature using ONLY the supplied certificate.
This is not a test of a particular recovery's trust store or installation code.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile


def verify(archive: Path, certificate: Path, certificate_sha256: str) -> dict:
    cert_der = subprocess.run(
        ["openssl", "x509", "-in", str(certificate), "-outform", "DER"],
        check=True, capture_output=True, timeout=15,
    ).stdout
    fingerprint = hashlib.sha256(cert_der).hexdigest()
    if fingerprint != certificate_sha256.lower():
        raise ValueError("Supplied certificate does not match the expected fingerprint")

    with archive.open("rb") as src, tempfile.TemporaryDirectory(prefix="forgeos-ota-") as tmp:
        src.seek(0, 2)
        length = src.tell()
        if length < 28:
            raise ValueError("Archive too short")
        src.seek(-6, 2)
        footer = src.read(6)
        signature_start, marker, comment_size = struct.unpack("<HHH", footer)
        if marker != 0xFFFF or not 6 < signature_start <= comment_size:
            raise ValueError("Invalid Android signature footer")
        eocd_size = comment_size + 22
        if length < eocd_size:
            raise ValueError("EOCD exceeds archive length")
        src.seek(-eocd_size, 2)
        eocd = src.read(eocd_size)
        if not eocd.startswith(b"PK\x05\x06") or b"PK\x05\x06" in eocd[4:]:
            raise ValueError("Invalid or ambiguous EOCD marker")
        if struct.unpack_from("<H", eocd, 20)[0] != comment_size:
            raise ValueError("EOCD comment length disagrees with footer")

        signed_length = length - comment_size - 2
        signature = eocd[-signature_start:-6]
        sig_path = Path(tmp) / "signature.der"
        content_path = Path(tmp) / "signed-content"
        sig_path.write_bytes(signature)
        src.seek(0)
        archive_hash = hashlib.sha256()
        with content_path.open("wb") as dst:
            remaining = signed_length
            while remaining:
                chunk = src.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Truncated archive")
                dst.write(chunk)
                archive_hash.update(chunk)
                remaining -= len(chunk)
        archive_hash.update(src.read())

        result = subprocess.run(
            ["openssl", "cms", "-verify", "-binary", "-inform", "DER",
             "-in", str(sig_path), "-content", str(content_path),
             "-nointern", "-certfile", str(certificate.resolve()), "-noverify",
             "-out", "/dev/null"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode:
            raise ValueError("Whole-file signature failed: " + result.stderr.strip())

    return {
        "archive": archive.name,
        "archive_bytes": length,
        "archive_sha256": archive_hash.hexdigest(),
        "certificate_sha256": fingerprint,
        "signed_bytes": signed_length,
        "signature_bytes": len(signature),
        "whole_file_signature_verified": True,
        "method": "Android OTA footer bounds + detached OpenSSL CMS; pinned external certificate only",
        "limitation": "Does not establish publisher identity independently or recovery trust-store acceptance",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("certificate_sha256")
    args = parser.parse_args()
    try:
        result = verify(args.archive, args.certificate, args.certificate_sha256)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Verification failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

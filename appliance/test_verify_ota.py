"""Synthetic OTA signatures exercise corruption and signer rejection."""

import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zipfile

from appliance.verify_ota import verify


class OtaVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="forgeos-ota-test-")
        cls.root = Path(cls.temp.name)
        cls.certs = []
        for name in ("publisher", "other"):
            key, cert = cls.root / (name + ".key"), cls.root / (name + ".pem")
            subprocess.run(
                ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                 "-keyout", str(key), "-out", str(cert), "-days", "1",
                 "-subj", "/CN=Disposable Test " + name],
                check=True, capture_output=True, timeout=15,
            )
            der = subprocess.run(
                ["openssl", "x509", "-in", str(cert), "-outform", "DER"],
                check=True, capture_output=True, timeout=10,
            ).stdout
            cls.certs.append((key, cert, hashlib.sha256(der).hexdigest()))
        unsigned = cls.root / "unsigned.zip"
        with zipfile.ZipFile(unsigned, "w") as z:
            z.writestr("system/example", b"original payload")
        content = cls.root / "content"
        content.write_bytes(unsigned.read_bytes()[:-2])
        sig = cls.root / "signature.der"
        key, cert, _ = cls.certs[0]
        subprocess.run(
            ["openssl", "cms", "-sign", "-binary", "-noattr", "-md", "sha256",
             "-in", str(content), "-signer", str(cert), "-inkey", str(key),
             "-outform", "DER", "-out", str(sig)],
            check=True, capture_output=True, timeout=10,
        )
        n = len(sig.read_bytes()) + 6
        cls.good = (content.read_bytes() + struct.pack("<H", n)
                    + sig.read_bytes() + struct.pack("<HHH", n, 0xFFFF, n))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check_archive(self, data, signer=0, fingerprint=None):
        archive = self.root / "test.zip"
        archive.write_bytes(data)
        _, cert, expected = self.certs[signer]
        return verify(archive, cert, fingerprint or expected)

    def test_valid_signature_and_archive_hash(self):
        result = self.check_archive(self.good)
        self.assertTrue(result["whole_file_signature_verified"])
        self.assertEqual(result["archive_sha256"], hashlib.sha256(self.good).hexdigest())

    def test_payload_tamper_rejected(self):
        bad = self.good.replace(b"original payload", b"modified payload")
        with self.assertRaisesRegex(ValueError, "signature failed"):
            self.check_archive(bad)

    def test_other_pinned_signer_rejected(self):
        with self.assertRaisesRegex(ValueError, "signature failed"):
            self.check_archive(self.good, signer=1)

    def test_wrong_certificate_fingerprint_rejected(self):
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.check_archive(self.good, fingerprint="0" * 64)

    def test_footer_marker_rejected(self):
        bad = bytearray(self.good)
        bad[-4] = 0
        with self.assertRaisesRegex(ValueError, "footer"):
            self.check_archive(bad)

    def test_eocd_length_mismatch_rejected(self):
        bad = bytearray(self.good)
        eocd = bad.index(b"PK\x05\x06")
        bad[eocd + 20] ^= 1
        with self.assertRaisesRegex(ValueError, "comment length"):
            self.check_archive(bad)

    def test_ambiguous_eocd_rejected(self):
        bad = bytearray(self.good)
        bad[-10:-6] = b"PK\x05\x06"
        with self.assertRaisesRegex(ValueError, "EOCD"):
            self.check_archive(bad)

    def test_truncation_rejected(self):
        with self.assertRaises(ValueError):
            self.check_archive(self.good[:-6])


if __name__ == "__main__":
    unittest.main()

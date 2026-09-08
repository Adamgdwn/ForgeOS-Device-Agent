"""Verify all install inputs against the reviewed appliance contract. No device I/O."""

import argparse
import hashlib
import json
from pathlib import Path

from appliance.verify_ota import verify

CONTRACT = Path(__file__).with_name("gteslte-ytm-appliance-contract.json")


def check_candidate(directory: Path) -> dict:
    contract = json.loads(CONTRACT.read_text())
    rom = contract["candidate"]
    google = contract["google_services"]
    policy = contract["recovery_policy"]
    inputs = [
        (rom["rom_asset"], rom["rom_bytes"], rom["rom_sha256"]),
        (rom["recovery_asset"], rom["recovery_bytes"], rom["recovery_sha256"]),
        (google["asset"], google["asset_bytes"], google["asset_sha256"]),
        (policy["asset"], policy["asset_bytes"], policy["asset_sha256"]),
    ]
    results = []
    for name, size, expected in inputs:
        if name != Path(name).name:
            raise ValueError("Contract input must be a basename")
        path = directory / name
        if path.stat().st_size != size:
            raise ValueError(f"Size mismatch: {name}")
        with path.open("rb") as src:
            actual = hashlib.file_digest(src, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"SHA-256 mismatch: {name}")
        results.append({"name": name, "bytes": size, "sha256": actual})
    signature = verify(directory / google["asset"], directory / "release.x509.pem",
                       google["signer_certificate_sha256"])
    return {"contract": CONTRACT.name, "verified_inputs": results,
            "google_services_signature": signature,
            "device_installation_or_playback_verified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        result = check_candidate(args.directory)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Candidate verification failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from app.core.models import DeviceFingerprint, Transport


def slugify(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return cleaned or fallback


def build_fingerprint(
    manufacturer: str | None,
    model: str | None,
    serial: str | None,
    transport: Transport,
) -> DeviceFingerprint:
    basis = "|".join(
        [
            manufacturer or "unknown",
            model or "unknown",
            serial or "unknown",
            transport.value,
        ]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return DeviceFingerprint(
        manufacturer=manufacturer,
        model=model,
        serial=serial,
        transport=transport,
        short_fingerprint=digest[:8],
        stable_key=digest,
    )


def canonical_session_name(fingerprint: DeviceFingerprint, today: datetime | None = None) -> str:
    current = today or datetime.now()
    date_part = current.strftime("%Y%m%d")
    manufacturer = slugify(fingerprint.manufacturer or "unknown")
    model = slugify(fingerprint.model or "unknown")
    return f"{manufacturer}-{model}-{fingerprint.short_fingerprint}-{date_part}"


def generate_codename(fingerprint: DeviceFingerprint) -> str:
    manufacturer = slugify(fingerprint.manufacturer or "forge")
    return f"{manufacturer[:6]}-{fingerprint.short_fingerprint[:4]}"

from __future__ import annotations


def probe() -> dict[str, object]:
    return {
        "adapter": "samsung-download",
        "status": "stub",
        "notes": "Reserved for Heimdall or Samsung download-mode specific probing.",
    }

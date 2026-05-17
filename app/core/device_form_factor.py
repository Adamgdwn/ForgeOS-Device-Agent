from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from app.core.models import DeviceFormFactor


def infer_device_form_factor(device: dict[str, Any] | Any) -> tuple[DeviceFormFactor, str, float]:
    """Infer whether an Android-family device is a phone or tablet.

    This intentionally starts deterministic and explainable. Gemma can reason over
    the same persisted evidence later in the runtime, while the GUI selector keeps
    the operator in control when model numbers are ambiguous.
    """
    payload = _to_plain_dict(device)
    explicit = _explicit_form_factor(payload)
    if explicit:
        return explicit

    haystack = _flatten_text(payload)
    model = str(payload.get("model") or "").strip()
    model_upper = model.upper().replace(" ", "")
    codename = str(payload.get("device_codename") or "").lower()

    if re.match(r"^(SM-T|GT-P|SCH-I800|SGH-I497)", model_upper):
        return DeviceFormFactor.TABLET, "model_prefix", 0.92
    if re.match(r"^(SM-A|SM-G|SM-N|SM-S|GT-I|SGH-I|SAMSUNG-SM-G)", model_upper):
        return DeviceFormFactor.PHONE, "model_prefix", 0.86
    model_lower = model.lower()
    if re.search(r"\bgalaxy (s|a|note)[0-9]", model_lower):
        return DeviceFormFactor.PHONE, "model_name", 0.82

    tablet_terms = [
        "tablet",
        "galaxy tab",
        "pixel tablet",
        "nexus 7",
        "nexus 10",
        "kindle fire",
        "lenovo tb",
        "mediapad",
        "xoom",
        "surface duo",
    ]
    phone_terms = [
        "phone",
        "pixel ",
        "moto g",
        "oneplus",
        "iphone",
    ]
    if any(term in haystack for term in tablet_terms) or codename.startswith("gta"):
        return DeviceFormFactor.TABLET, "device_text", 0.8
    if any(term in haystack for term in phone_terms):
        return DeviceFormFactor.PHONE, "device_text", 0.75

    return DeviceFormFactor.UNKNOWN, "insufficient_evidence", 0.0


def apply_form_factor_inference(profile: Any, probe_data: dict[str, Any] | None = None) -> None:
    override = getattr(profile, "form_factor_override", None)
    if override and override != DeviceFormFactor.UNKNOWN:
        profile.form_factor = override
        profile.form_factor_source = "operator_override"
        profile.form_factor_confidence = 1.0
        return

    evidence = _to_plain_dict(profile)
    for generated_key in (
        "form_factor",
        "form_factor_source",
        "form_factor_confidence",
        "form_factor_override",
    ):
        evidence.pop(generated_key, None)
    if probe_data:
        evidence |= probe_data
    form_factor, source, confidence = infer_device_form_factor(evidence)
    profile.form_factor = form_factor
    profile.form_factor_source = source
    profile.form_factor_confidence = confidence


def _explicit_form_factor(payload: dict[str, Any]) -> tuple[DeviceFormFactor, str, float] | None:
    for key in ("form_factor", "device_form_factor", "ro.build.characteristics", "characteristics"):
        raw = payload.get(key)
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if "tablet" in text:
            return DeviceFormFactor.TABLET, key, 0.95
        if "phone" in text:
            return DeviceFormFactor.PHONE, key, 0.95

    raw_event = payload.get("raw_event")
    if isinstance(raw_event, dict):
        nested = _explicit_form_factor(raw_event)
        if nested:
            return nested
    snapshot = payload.get("hardware_snapshot")
    if isinstance(snapshot, dict):
        nested = _explicit_form_factor(snapshot)
        if nested:
            return nested
    return None


def _to_plain_dict(value: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return dict(getattr(value, "__dict__", {}))


def _flatten_text(value: Any) -> str:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, Enum):
            parts.append(item.value)
        elif isinstance(item, dict):
            for key, val in item.items():
                parts.append(str(key))
                walk(val)
        elif isinstance(item, (list, tuple, set)):
            for val in item:
                walk(val)
        elif item is not None:
            parts.append(str(item))

    walk(value)
    return " ".join(parts).lower()

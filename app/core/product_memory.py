from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.io_utils import atomic_write_json
from app.core.models import DeviceProfile, SessionState, utc_now


class ProductMemoryEngine:
    """Durable product/version memory for devices ForgeOS has touched."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.knowledge_dir = root / "knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.knowledge_dir / "product_memory.json"

    def record_observation(
        self,
        *,
        session_dir: Path,
        profile: DeviceProfile,
        state: SessionState,
        assessment: dict[str, Any],
        build_plan: dict[str, Any],
        build_artifacts: dict[str, Any],
        blocker: dict[str, Any],
        recommendation: dict[str, Any],
        restore_plan: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._load()
        products = payload.setdefault("products", {})
        requested_product_key = self.product_key(profile)
        product_key = self._canonical_product_key(products, requested_product_key, profile)
        version_key = self.version_key(profile)
        now = utc_now()

        product = products.setdefault(
            product_key,
            {
                "product_key": product_key,
                "manufacturer": profile.manufacturer or "Unknown",
                "model": profile.model or "Unknown",
                "codenames": [],
                "form_factors": [],
                "first_seen": now,
                "last_seen": now,
                "observations": 0,
                "sessions": [],
                "versions": {},
                "aliases": [],
                "related_identities": [],
                "reusable_guidance": [],
            },
        )
        self._merge_weaker_products(products, product_key, profile, now)
        product["last_seen"] = now
        product["observations"] = int(product.get("observations", 0)) + 1
        product["manufacturer"] = self._prefer_specific(product.get("manufacturer"), profile.manufacturer)
        product["model"] = self._prefer_specific(product.get("model"), profile.model)
        self._append_unique(product.setdefault("aliases", []), requested_product_key)
        self._append_unique(product["codenames"], profile.device_codename or "unknown")
        self._append_unique(product["form_factors"], getattr(profile.form_factor, "value", str(profile.form_factor)))
        self._append_session(product, session_dir.name)

        version = product["versions"].setdefault(
            version_key,
            {
                "version_key": version_key,
                "android_version": profile.android_version or "unknown",
                "build_fingerprint": profile.fingerprint or "",
                "build_id": self._build_id(profile),
                "first_seen": now,
                "last_seen": now,
                "observations": 0,
                "support_status_counts": {},
                "strategies": {},
                "recommended_paths": {},
                "recommended_use_cases": {},
                "blockers": {},
                "artifact_history": [],
                "source_history": [],
                "restore_history": [],
                "lessons": [],
            },
        )
        version["last_seen"] = now
        version["observations"] = int(version.get("observations", 0)) + 1
        self._count(version["support_status_counts"], assessment.get("support_status", "unknown"))
        self._count(version["strategies"], state.selected_strategy or "unselected")
        self._count(version["recommended_paths"], build_plan.get("os_path", "unknown"))
        self._count(version["recommended_use_cases"], recommendation.get("recommended_use_case", "unknown"))
        self._count(version["blockers"], blocker.get("blocker_type", "none"))
        self._append_limited(
            version["artifact_history"],
            {
                "recorded_at": now,
                "status": build_artifacts.get("status"),
                "install_mode": (build_artifacts.get("details") or {}).get("install_mode"),
                "staged_count": len(build_artifacts.get("artifacts") or []),
                "missing_requirements": (build_artifacts.get("details") or {}).get("missing_requirements", []),
            },
        )
        self._append_limited(
            version["source_history"],
            {
                "recorded_at": now,
                "status": (build_plan.get("source_acquisition") or {}).get("status"),
                "resolver_status": ((build_plan.get("source_acquisition") or {}).get("resolver") or {}).get("status"),
                "builder_status": ((build_plan.get("source_acquisition") or {}).get("builder") or {}).get("status"),
                "builder_reason": ((build_plan.get("source_acquisition") or {}).get("builder") or {}).get("reason"),
            },
        )
        self._append_limited(
            version["restore_history"],
            {
                "recorded_at": now,
                "status": restore_plan.get("status"),
                "summary": restore_plan.get("summary"),
                "restore_path_feasible": bool(assessment.get("restore_path_feasible")),
            },
        )
        version["lessons"] = self._compiled_lessons(version, profile)
        product["reusable_guidance"] = self._compiled_product_guidance(product)
        self._refresh_related_identities(products)

        payload["generated_at"] = now
        atomic_write_json(self.path, payload)
        return {
            "product_key": product_key,
            "requested_product_key": requested_product_key,
            "version_key": version_key,
            "product": product,
            "version": version,
            "memory_path": str(self.path),
        }

    def lookup(self, profile: DeviceProfile) -> dict[str, Any]:
        payload = self._load()
        requested_product_key = self.product_key(profile)
        products = payload.get("products", {})
        product_key = self._canonical_product_key(products, requested_product_key, profile)
        product = payload.get("products", {}).get(product_key)
        if not product:
            return {
                "has_product_memory": False,
                "product_key": product_key,
                "requested_product_key": requested_product_key,
                "version_key": self.version_key(profile),
                "memory_path": str(self.path),
            }
        version_key = self.version_key(profile)
        return {
            "has_product_memory": True,
            "product_key": product_key,
            "requested_product_key": requested_product_key,
            "version_key": version_key,
            "memory_path": str(self.path),
            "observations": product.get("observations", 0),
            "product": product,
            "aliases": product.get("aliases", []),
            "related_identities": product.get("related_identities", []),
            "reusable_guidance": product.get("reusable_guidance", []),
            "known_versions": list((product.get("versions") or {}).keys()),
            "version": (product.get("versions") or {}).get(version_key, {}),
        }

    def product_key(self, profile: DeviceProfile) -> str:
        manufacturer = self._slug(profile.manufacturer or "unknown")
        model = self._slug(profile.model or "unknown")
        codename = self._slug(profile.device_codename or "unknown")
        return f"{manufacturer}:{model}:{codename}"

    def version_key(self, profile: DeviceProfile) -> str:
        android_version = self._slug(profile.android_version or "unknown")
        build_id = self._slug(self._build_id(profile) or "unknown")
        fingerprint = profile.fingerprint or ""
        digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:10] if fingerprint else "nofp"
        return f"android-{android_version}:build-{build_id}:fp-{digest}"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"generated_at": utc_now(), "products": {}}
        try:
            loaded = json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {"generated_at": utc_now(), "products": {}}
        return loaded if isinstance(loaded, dict) else {"generated_at": utc_now(), "products": {}}

    def _canonical_product_key(
        self,
        products: dict[str, dict[str, Any]],
        requested_key: str,
        profile: DeviceProfile,
    ) -> str:
        for existing_key, product in products.items():
            if requested_key in (product.get("aliases") or []):
                return existing_key

        compatible_keys = [
            key
            for key in products
            if self._compatible_product_key(key, requested_key, profile)
        ]
        if not compatible_keys:
            return requested_key

        requested_quality = self._identity_quality(requested_key)
        best_existing = max(compatible_keys, key=self._identity_quality)
        best_quality = self._identity_quality(best_existing)
        if best_quality > requested_quality:
            return best_existing
        return requested_key

    def _merge_weaker_products(
        self,
        products: dict[str, dict[str, Any]],
        canonical_key: str,
        profile: DeviceProfile,
        merged_at: str,
    ) -> None:
        canonical = products[canonical_key]
        canonical_quality = self._identity_quality(canonical_key)
        for other_key in list(products):
            if other_key == canonical_key:
                continue
            if not self._compatible_product_key(other_key, canonical_key, profile):
                continue
            if self._identity_quality(other_key) >= canonical_quality:
                continue
            source = products.pop(other_key)
            self._merge_product(canonical, source, source_key=other_key, merged_at=merged_at)

    def _merge_product(
        self,
        target: dict[str, Any],
        source: dict[str, Any],
        *,
        source_key: str,
        merged_at: str,
    ) -> None:
        target["first_seen"] = min(str(target.get("first_seen") or merged_at), str(source.get("first_seen") or merged_at))
        target["last_seen"] = max(str(target.get("last_seen") or merged_at), str(source.get("last_seen") or merged_at))
        target["observations"] = int(target.get("observations", 0)) + int(source.get("observations", 0))
        target["manufacturer"] = self._prefer_specific(target.get("manufacturer"), source.get("manufacturer"))
        target["model"] = self._prefer_specific(target.get("model"), source.get("model"))

        for field_name in ("codenames", "form_factors", "sessions", "reusable_guidance"):
            target_values = target.setdefault(field_name, [])
            for value in source.get(field_name) or []:
                self._append_unique(target_values, value)
            if field_name == "sessions":
                target[field_name] = target[field_name][-12:]

        aliases = target.setdefault("aliases", [])
        self._append_unique(aliases, source_key)
        for alias in source.get("aliases") or []:
            self._append_unique(aliases, alias)

        merged_products = target.setdefault("merged_products", [])
        self._append_limited(
            merged_products,
            {
                "product_key": source_key,
                "merged_at": merged_at,
                "reason": "merged weaker compatible product identity",
            },
            limit=30,
        )

        target_versions = target.setdefault("versions", {})
        for version_key, source_version in (source.get("versions") or {}).items():
            if version_key not in target_versions:
                target_versions[version_key] = source_version
                continue
            self._merge_version(target_versions[version_key], source_version, merged_at)

    def _merge_version(self, target: dict[str, Any], source: dict[str, Any], merged_at: str) -> None:
        target["first_seen"] = min(str(target.get("first_seen") or merged_at), str(source.get("first_seen") or merged_at))
        target["last_seen"] = max(str(target.get("last_seen") or merged_at), str(source.get("last_seen") or merged_at))
        target["observations"] = int(target.get("observations", 0)) + int(source.get("observations", 0))
        for field_name in ("support_status_counts", "strategies", "recommended_paths", "recommended_use_cases", "blockers"):
            target_mapping = target.setdefault(field_name, {})
            for key, count in (source.get(field_name) or {}).items():
                target_mapping[str(key)] = int(target_mapping.get(str(key), 0)) + int(count)
        for field_name in ("artifact_history", "source_history", "restore_history"):
            target_values = target.setdefault(field_name, [])
            target_values.extend(source.get(field_name) or [])
            del target_values[:-20]
        for lesson in source.get("lessons") or []:
            self._append_unique(target.setdefault("lessons", []), lesson)

    def _refresh_related_identities(self, products: dict[str, dict[str, Any]]) -> None:
        product_items = list(products.items())
        for product_key, product in product_items:
            related: list[str] = []
            for other_key, _other in product_items:
                if other_key == product_key:
                    continue
                if self._compatible_product_key(other_key, product_key, None):
                    related.append(other_key)
            product["related_identities"] = sorted(related)

    def _compatible_product_key(
        self,
        existing_key: str,
        requested_key: str,
        profile: DeviceProfile | None,
    ) -> bool:
        existing_manufacturer, existing_model, existing_codename = self._product_key_parts(existing_key)
        requested_manufacturer, requested_model, requested_codename = self._product_key_parts(requested_key)
        if self._is_specific(existing_codename) and existing_codename == requested_codename:
            return True
        if (
            self._is_specific(existing_manufacturer)
            and self._is_specific(existing_model)
            and existing_manufacturer == requested_manufacturer
            and existing_model == requested_model
        ):
            return True
        if profile:
            codename = self._slug(profile.device_codename or "unknown")
            if self._is_specific(codename) and existing_codename == codename:
                return True
        return False

    def _product_key_parts(self, product_key: str) -> tuple[str, str, str]:
        parts = product_key.split(":")
        padded = (parts + ["unknown", "unknown", "unknown"])[:3]
        return padded[0], padded[1], padded[2]

    def _identity_quality(self, product_key: str) -> int:
        manufacturer, model, codename = self._product_key_parts(product_key)
        score = 0
        if self._is_specific(manufacturer):
            score += 1
        if self._is_specific(model):
            score += 1
        if self._is_specific(codename):
            score += 2
        return score

    def _prefer_specific(self, current: Any, candidate: Any) -> str:
        current_value = str(current or "Unknown")
        candidate_value = str(candidate or "")
        if not self._is_specific(self._slug(current_value)) and self._is_specific(self._slug(candidate_value)):
            return candidate_value
        return current_value

    def _is_specific(self, value: str) -> bool:
        return self._slug(value) not in {
            "",
            "unknown",
            "none",
            "null",
            "usb-attached-android",
            "android",
            "generic",
            "device",
        }

    def _build_id(self, profile: DeviceProfile) -> str:
        raw = dict(profile.raw_probe_data or {})
        snapshot = dict(raw.get("hardware_snapshot") or {})
        return str(
            snapshot.get("build_id")
            or snapshot.get("incremental")
            or raw.get("build_id")
            or raw.get("build_incremental")
            or ""
        )

    def _compiled_lessons(self, version: dict[str, Any], profile: DeviceProfile) -> list[str]:
        lessons: list[str] = []
        source_history = list(version.get("source_history") or [])
        if any(str(item.get("builder_reason") or "").startswith("Android repo tool is missing") for item in source_history):
            lessons.append("Local Android source builds need the Android repo tool before retrying.")
        if any(item.get("status") == "blocked_by_host_prerequisite" for item in source_history):
            lessons.append("Skip repeated source build attempts until host prerequisites change.")
        blockers = dict(version.get("blockers") or {})
        if blockers.get("source_blocker", 0) >= 2:
            lessons.append("This version repeatedly reaches source acquisition; prioritize real firmware or known aftermarket packages.")
        artifact_history = list(version.get("artifact_history") or [])
        if artifact_history and not any(item.get("status") == "ready" for item in artifact_history):
            lessons.append("No usable flashable artifact has been proven for this version yet.")
        if profile.device_codename:
            lessons.append(f"Reuse codename `{profile.device_codename}` when searching firmware, recovery, and aftermarket builds.")
        return self._dedupe(lessons)

    def _compiled_product_guidance(self, product: dict[str, Any]) -> list[str]:
        guidance: list[str] = []
        versions = list((product.get("versions") or {}).values())
        if any("source acquisition" in " ".join(version.get("lessons", [])).lower() for version in versions):
            guidance.append("Expect source/firmware acquisition to be the main blocker for this product family.")
        if any("repo tool" in " ".join(version.get("lessons", [])).lower() for version in versions):
            guidance.append("Check host Android build prerequisites before launching local source builds.")
        codenames = [codename for codename in product.get("codenames", []) if codename and codename != "unknown"]
        if codenames:
            guidance.append(f"Known codenames for reuse: {', '.join(sorted(set(codenames)))}.")
        return self._dedupe(guidance)

    def _append_unique(self, values: list[str], value: str) -> None:
        if value and value not in values:
            values.append(value)

    def _append_session(self, product: dict[str, Any], session_name: str) -> None:
        sessions = list(product.get("sessions") or [])
        if session_name in sessions:
            sessions.remove(session_name)
        sessions.append(session_name)
        product["sessions"] = sessions[-12:]

    def _append_limited(self, values: list[dict[str, Any]], item: dict[str, Any], limit: int = 20) -> None:
        values.append(item)
        del values[:-limit]

    def _count(self, mapping: dict[str, int], key: Any) -> None:
        normalized = str(key or "unknown")
        mapping[normalized] = int(mapping.get(normalized, 0)) + 1

    def _dedupe(self, values: list[str]) -> list[str]:
        seen = set()
        output = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            output.append(value)
        return output

    def _slug(self, value: str) -> str:
        return "-".join(str(value).strip().lower().replace("_", "-").split()) or "unknown"

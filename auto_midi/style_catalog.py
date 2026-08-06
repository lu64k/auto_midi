"""Validated hot-reloadable source of truth for drum styles and grooves."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Callable


DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "catalog" / "drum_styles.json"


@dataclass(frozen=True)
class CatalogSnapshot:
    payload: dict[str, Any]
    version: int
    content_hash: str
    mtime_ns: int

    @property
    def styles(self) -> dict[str, Any]:
        return self.payload["styles"]


class GrooveCatalogProvider:
    """Reload a catalog atomically when its file changes."""

    def __init__(self, path: Path | None = None, warning_sink: Callable[[str], None] | None = None):
        configured = os.getenv("AUTO_MIDI_STYLE_CATALOG", "").strip()
        self.path = Path(path or configured or DEFAULT_CATALOG_PATH)
        self.warning_sink = warning_sink or (lambda message: print(f"[style_catalog] {message}", flush=True))
        self._lock = threading.RLock()
        self._snapshot: CatalogSnapshot | None = None
        self._failed_hash: str | None = None

    def get(self) -> CatalogSnapshot:
        with self._lock:
            try:
                raw = self.path.read_bytes()
                digest = "sha256:" + hashlib.sha256(raw).hexdigest()
                if self._snapshot is not None and self._snapshot.content_hash == digest:
                    return self._snapshot
                if self._snapshot is not None and self._failed_hash == digest:
                    return self._snapshot
                payload = json.loads(raw.decode("utf-8"))
                validate_catalog(payload)
                snapshot = CatalogSnapshot(
                    payload=payload,
                    version=int(payload["version"]),
                    content_hash=digest,
                    mtime_ns=self.path.stat().st_mtime_ns,
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                if self._snapshot is None:
                    raise ValueError(f"style catalog is invalid: {exc}") from exc
                self._failed_hash = digest if "digest" in locals() else "missing"
                self.warning_sink(f"catalog reload rejected; keeping version {self._snapshot.version}: {exc}")
                return self._snapshot
            self._snapshot = snapshot
            self._failed_hash = None
            return snapshot


def validate_catalog(payload: Any) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), int):
        raise ValueError("catalog requires an integer version")
    styles = payload.get("styles")
    if not isinstance(styles, dict) or not styles or "free" not in styles:
        raise ValueError("catalog requires a non-empty styles object containing free")
    seen_grooves: set[str] = set()
    for style_name, style in styles.items():
        if not isinstance(style_name, str) or not style_name.strip() or not isinstance(style, dict):
            raise ValueError("catalog contains an invalid style")
        grooves = style.get("grooves")
        default = style.get("default_groove")
        if not isinstance(grooves, dict) or not grooves or default not in grooves:
            raise ValueError(f"style {style_name} requires grooves and a valid default_groove")
        if not isinstance(style.get("dna_bounds", {}), dict):
            raise ValueError(f"style {style_name} dna_bounds must be an object")
        for groove_name, groove in grooves.items():
            if groove_name in seen_grooves:
                raise ValueError(f"groove {groove_name} belongs to more than one style")
            seen_grooves.add(groove_name)
            _validate_groove(style_name, groove_name, groove)


def _validate_groove(style_name: str, groove_name: str, groove: Any) -> None:
    if not isinstance(groove_name, str) or not groove_name.strip() or not isinstance(groove, dict):
        raise ValueError(f"style {style_name} contains an invalid groove")
    profile = groove.get("profile")
    if not isinstance(profile, dict):
        raise ValueError(f"groove {groove_name} requires a profile")
    for field in ("skeleton_strength", "backbeat_variation", "ornament_amount"):
        value = profile.get(field)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"groove {groove_name} profile {field} must be between 0 and 1")
    if groove.get("anchor") not in {"strong_one", "one_drop", "four_on_floor", "offbeat_push", "floating"}:
        raise ValueError(f"groove {groove_name} has an invalid anchor")
    pulse = groove.get("pulse")
    if pulse is not None and pulse not in {4, 8, 16}:
        raise ValueError(f"groove {groove_name} pulse must be 4, 8, 16, or null")
    pattern = groove.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, dict):
            raise ValueError(f"groove {groove_name} pattern must be an object")
        for field in ("kick_steps", "snare_steps", "hat_steps"):
            steps = pattern.get(field)
            if not isinstance(steps, list) or any(not isinstance(step, int) or not 0 <= step < 16 for step in steps):
                raise ValueError(f"groove {groove_name} {field} must use 0-15 steps")


CATALOG = GrooveCatalogProvider()


def catalog_snapshot() -> CatalogSnapshot:
    return CATALOG.get()


def style_names() -> tuple[str, ...]:
    return tuple(catalog_snapshot().styles)


def style_exists(style: str | None) -> bool:
    return bool(style and style in catalog_snapshot().styles)


def groove_owner(groove: str | None) -> str | None:
    if not groove:
        return None
    for style_name, style in catalog_snapshot().styles.items():
        if groove in style["grooves"]:
            return style_name
    return None


def groove_data(groove: str) -> dict[str, Any] | None:
    owner = groove_owner(groove)
    return catalog_snapshot().styles[owner]["grooves"][groove] if owner else None


class DynamicCatalogMapping(Mapping[str, Any]):
    def __init__(self, builder: Callable[[CatalogSnapshot], dict[str, Any]]):
        self.builder = builder

    def _data(self) -> dict[str, Any]:
        return self.builder(catalog_snapshot())

    def __getitem__(self, key: str) -> Any:
        return self._data()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())


STYLE_BOUNDS: Mapping[str, Any] = DynamicCatalogMapping(
    lambda snapshot: {name: style.get("dna_bounds", {}) for name, style in snapshot.styles.items()}
)

"""Step-based groove patterns loaded from the live style catalog."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .style_catalog import DynamicCatalogMapping, catalog_snapshot, groove_data


@dataclass(frozen=True)
class RockPattern:
    name: str
    kick_steps: tuple[int, ...]
    snare_steps: tuple[int, ...]
    hat_steps: tuple[int, ...]
    swing_ratio: float = 0.0


def _patterns(snapshot) -> dict[str, RockPattern]:
    result = {}
    for style in snapshot.styles.values():
        for name, groove in style["grooves"].items():
            pattern = groove.get("pattern")
            if pattern:
                result[name] = RockPattern(
                    name=name,
                    kick_steps=tuple(pattern["kick_steps"]),
                    snare_steps=tuple(pattern["snare_steps"]),
                    hat_steps=tuple(pattern["hat_steps"]),
                    swing_ratio=float(pattern.get("swing_ratio", 0.0)),
                )
    return result


ROCK_PATTERNS: Mapping[str, RockPattern] = DynamicCatalogMapping(_patterns)


def rock_pattern(name: str) -> RockPattern | None:
    data = groove_data(name)
    pattern = data.get("pattern") if data else None
    if not pattern:
        return None
    return RockPattern(
        name=name,
        kick_steps=tuple(pattern["kick_steps"]),
        snare_steps=tuple(pattern["snare_steps"]),
        hat_steps=tuple(pattern["hat_steps"]),
        swing_ratio=float(pattern.get("swing_ratio", 0.0)),
    )


def pattern_steps(pattern: RockPattern, field: str, steps_per_bar: int) -> tuple[int, ...]:
    source_steps = getattr(pattern, field)
    if steps_per_bar == 16:
        return source_steps
    return tuple(dict.fromkeys(min(steps_per_bar - 1, round(step * steps_per_bar / 16)) for step in source_steps))

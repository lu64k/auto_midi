"""Step-based Rock groove patterns.

Patterns define the recognizable skeleton. The event generator may add bounded
ornaments, lyrics accents, and fills around this skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RockPattern:
    name: str
    kick_steps: tuple[int, ...]
    snare_steps: tuple[int, ...]
    hat_steps: tuple[int, ...]
    swing_ratio: float = 0.0


ROCK_PATTERNS = {
    "classic_rock": RockPattern(
        "classic_rock", (0, 8), (4, 12), tuple(range(0, 16, 2))
    ),
    "driving_rock": RockPattern(
        "driving_rock", (0, 4, 8, 12), (4, 12), tuple(range(0, 16, 2))
    ),
    "half_time_rock": RockPattern(
        "half_time_rock", (0, 8), (8,), tuple(range(0, 16, 2))
    ),
    "sparse_rock": RockPattern(
        "sparse_rock", (0, 8), (12,), (2, 6, 10, 14)
    ),
    "shuffle_rock": RockPattern(
        "shuffle_rock", (0, 8), (4, 12), (0, 2, 4, 6, 8, 10, 12, 14), 0.30
    ),
    "blues_rock": RockPattern(
        "blues_rock", (0, 6, 8, 10), (4, 12), (0, 2, 4, 6, 8, 10, 12, 14), 0.30
    ),
    "punk_rock": RockPattern(
        "punk_rock", tuple(range(0, 16, 2)), (4, 12), tuple(range(16))
    ),
    "indie_rock": RockPattern(
        "indie_rock", (0, 7, 8, 11), (4, 12), (0, 2, 6, 8, 10, 14)
    ),
    "hard_rock": RockPattern(
        "hard_rock", (0, 4, 8, 10, 12), (4, 12), tuple(range(0, 16, 2))
    ),
    "arena_rock": RockPattern(
        "arena_rock", (0, 8), (4, 12), tuple(range(0, 16, 2))
    ),
    "double_kick_rock": RockPattern(
        "double_kick_rock", tuple(range(0, 16, 2)), (4, 12), tuple(range(0, 16, 2))
    ),
    "half_time_hard_rock": RockPattern(
        "half_time_hard_rock", (0, 8, 10), (8,), tuple(range(0, 16, 2))
    ),
    "sparse_dream": RockPattern(
        "sparse_dream", (0,), (12,), (0, 6, 10), 0.0
    ),
    "washed_8th": RockPattern(
        "washed_8th", (0, 8), (4, 12), (0, 4, 8, 12), 0.0
    ),
    "post_rock_build": RockPattern(
        "post_rock_build", (0, 8), (4, 12), (0, 2, 4, 6, 8, 10, 12, 14)
    ),
    "post_rock_peak": RockPattern(
        "post_rock_peak", tuple(range(0, 16, 2)), (4, 12), tuple(range(16))
    ),
    "post_rock_release": RockPattern(
        "post_rock_release", (0,), (12,), (0, 8), 0.0
    ),
    "psych_shuffle": RockPattern(
        "psych_shuffle", (0, 6, 8, 10), (4, 12), (0, 2, 4, 6, 8, 10, 12, 14), 0.30
    ),
    "psych_groove": RockPattern(
        "psych_groove", (0, 7, 8, 11), (4, 12), (0, 2, 6, 8, 10, 14), 0.0
    ),
    "motorik_rock": RockPattern(
        "motorik_rock", (0, 4, 8, 12), (4, 12), tuple(range(0, 16, 2))
    ),
}


def rock_pattern(name: str) -> RockPattern | None:
    return ROCK_PATTERNS.get(name)


def pattern_steps(pattern: RockPattern, field: str, steps_per_bar: int) -> tuple[int, ...]:
    """Scale the 4/4 pattern onto another supported bar grid."""
    source_steps = getattr(pattern, field)
    if steps_per_bar == 16:
        return source_steps
    return tuple(dict.fromkeys(min(steps_per_bar - 1, round(step * steps_per_bar / 16)) for step in source_steps))

from __future__ import annotations

from dataclasses import dataclass
import random

from .text_parser import TextMap


PRESET_BOUNDS = {
    "free": {},
    "boom_bap": {
        "swing": (0.08, 0.22),
        "syncopation": (0.25, 0.6),
        "high_density": (0.35, 0.7),
        "mid_bias": (0.6, 0.95),
    },
    "trap": {
        "pulse": (16, 16),
        "swing": (0.0, 0.08),
        "syncopation": (0.45, 0.9),
        "high_density": (0.55, 1.0),
        "low_bias": (0.55, 0.95),
    },
    "minimal": {
        "syncopation": (0.05, 0.35),
        "high_density": (0.1, 0.45),
        "mutation": (0.05, 0.3),
    },
    "rock": {
        "pulse": (8, 16),
        "swing": (0.0, 0.05),
        "syncopation": (0.1, 0.35),
        "low_bias": (0.65, 1.0),
        "mid_bias": (0.7, 1.0),
    },
}


@dataclass(frozen=True)
class DrummerDNA:
    pulse: int
    low_bias: float
    mid_bias: float
    high_density: float
    accent_follow: float
    rest_follow: float
    syncopation: float
    repetition: float
    mutation: float
    fill_aggression: float
    swing: float


def generate_dna(
    text_map: TextMap,
    rng: random.Random,
    complexity: int,
    intensity: int,
    fill: int,
    randomness: int,
    preset: str = "free",
) -> DrummerDNA:
    density = min(1.0, text_map.average_chars / 16.0)
    variation = _scale(randomness)
    complexity_value = _scale(complexity)
    intensity_value = _scale(intensity)
    fill_value = _scale(fill)
    bounds = PRESET_BOUNDS.get(preset, PRESET_BOUNDS["free"])

    pulse = _choose_pulse(rng, density, complexity_value, bounds)
    return DrummerDNA(
        pulse=pulse,
        low_bias=_bounded(rng, bounds, "low_bias", 0.35 + intensity_value * 0.45, variation),
        mid_bias=_bounded(rng, bounds, "mid_bias", 0.45 + intensity_value * 0.35, variation),
        high_density=_bounded(rng, bounds, "high_density", 0.2 + complexity_value * 0.65 + density * 0.15, variation),
        accent_follow=_clamp(0.35 + density * 0.35 + variation * 0.25),
        rest_follow=_clamp(0.25 + variation * 0.45),
        syncopation=_bounded(rng, bounds, "syncopation", 0.15 + complexity_value * 0.45, variation),
        repetition=_clamp(0.75 - variation * 0.5 + rng.uniform(-0.1, 0.1)),
        mutation=_bounded(rng, bounds, "mutation", 0.1 + variation * 0.55, variation),
        fill_aggression=_clamp(fill_value * (0.4 + complexity_value * 0.6) + rng.uniform(-0.1, 0.1)),
        swing=_bounded(rng, bounds, "swing", rng.uniform(0.0, 0.16) * (0.4 + complexity_value), variation),
    )


def _choose_pulse(
    rng: random.Random,
    density: float,
    complexity: float,
    bounds: dict[str, tuple[float, float]],
) -> int:
    if "pulse" in bounds:
        low, high = bounds["pulse"]
        return int(rng.choice([int(low), int(high)]))
    if density > 0.8 or complexity > 0.65:
        return rng.choice([16, 16, 8])
    if complexity < 0.25:
        return rng.choice([4, 8])
    return rng.choice([8, 16])


def _bounded(
    rng: random.Random,
    bounds: dict[str, tuple[float, float]],
    key: str,
    center: float,
    variation: float,
) -> float:
    if key in bounds:
        low, high = bounds[key]
        return rng.uniform(low, high)
    spread = 0.15 + variation * 0.35
    return _clamp(rng.uniform(center - spread, center + spread))


def _scale(value: int) -> float:
    return _clamp(value / 100.0)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))

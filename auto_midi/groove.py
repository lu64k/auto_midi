"""Named groove templates used to keep style identity stable."""

from __future__ import annotations


GROOVES_BY_STYLE = {
    "free": ("free",),
    "boom_bap": ("boom_bap",),
    "hiphop": ("hiphop",),
    "trap": ("trap",),
    "minimal": ("minimal",),
    "rock": ("classic_rock", "driving_rock", "half_time_rock", "sparse_rock"),
    "jazz": ("swing_ride", "jazz_waltz"),
    "blues": ("blues_shuffle", "slow_blues"),
    "rnb": ("rnb_soul", "rnb_modern"),
    "country": ("country_train", "two_beat_country"),
    "funk": ("classic_funk", "syncopated_funk"),
    "reggae": ("one_drop", "rockers", "ska_offbeat"),
}

DEFAULT_GROOVE_BY_STYLE = {
    "free": "free",
    "boom_bap": "boom_bap",
    "hiphop": "hiphop",
    "trap": "trap",
    "minimal": "minimal",
    "rock": "classic_rock",
    "jazz": "swing_ride",
    "blues": "blues_shuffle",
    "rnb": "rnb_soul",
    "country": "country_train",
    "funk": "classic_funk",
    "reggae": "one_drop",
}

# The anchor is the skeleton; density, fills, and text accents are layered on top.
GROOVE_ANCHORS = {
    "free": "floating",
    "boom_bap": "strong_one",
    "hiphop": "floating",
    "trap": "floating",
    "minimal": "strong_one",
    "classic_rock": "strong_one",
    "driving_rock": "four_on_floor",
    "half_time_rock": "strong_one",
    "sparse_rock": "strong_one",
    "swing_ride": "floating",
    "jazz_waltz": "floating",
    "blues_shuffle": "strong_one",
    "slow_blues": "strong_one",
    "rnb_soul": "offbeat_push",
    "rnb_modern": "floating",
    "country_train": "strong_one",
    "two_beat_country": "strong_one",
    "classic_funk": "offbeat_push",
    "syncopated_funk": "offbeat_push",
    "one_drop": "one_drop",
    "rockers": "strong_one",
    "ska_offbeat": "offbeat_push",
}

GROOVE_PULSES = {
    "classic_rock": 8,
    "driving_rock": 8,
    "half_time_rock": 8,
    "sparse_rock": 8,
    "boom_bap": 8,
    "hiphop": 8,
    "trap": 16,
    "minimal": 8,
    "swing_ride": 8,
    "jazz_waltz": 8,
    "blues_shuffle": 8,
    "slow_blues": 8,
    "rnb_soul": 16,
    "rnb_modern": 16,
    "country_train": 8,
    "two_beat_country": 8,
    "classic_funk": 16,
    "syncopated_funk": 16,
    "one_drop": 8,
    "rockers": 8,
    "ska_offbeat": 8,
}

GROOVE_PROFILES = {
    "free": {"skeleton_strength": 0.35, "backbeat_variation": 0.65, "ornament_amount": 0.70},
    "boom_bap": {"skeleton_strength": 0.80, "backbeat_variation": 0.20, "ornament_amount": 0.35},
    "hiphop": {"skeleton_strength": 0.65, "backbeat_variation": 0.40, "ornament_amount": 0.55},
    "trap": {"skeleton_strength": 0.55, "backbeat_variation": 0.45, "ornament_amount": 0.70},
    "minimal": {"skeleton_strength": 0.85, "backbeat_variation": 0.15, "ornament_amount": 0.15},
    "classic_rock": {"skeleton_strength": 0.85, "backbeat_variation": 0.15, "ornament_amount": 0.30},
    "driving_rock": {"skeleton_strength": 0.90, "backbeat_variation": 0.10, "ornament_amount": 0.35},
    "half_time_rock": {"skeleton_strength": 0.80, "backbeat_variation": 0.20, "ornament_amount": 0.25},
    "sparse_rock": {"skeleton_strength": 0.50, "backbeat_variation": 0.40, "ornament_amount": 0.08},
    "swing_ride": {"skeleton_strength": 0.70, "backbeat_variation": 0.45, "ornament_amount": 0.60},
    "jazz_waltz": {"skeleton_strength": 0.65, "backbeat_variation": 0.50, "ornament_amount": 0.60},
    "blues_shuffle": {"skeleton_strength": 0.85, "backbeat_variation": 0.20, "ornament_amount": 0.35},
    "slow_blues": {"skeleton_strength": 0.75, "backbeat_variation": 0.30, "ornament_amount": 0.25},
    "rnb_soul": {"skeleton_strength": 0.70, "backbeat_variation": 0.30, "ornament_amount": 0.65},
    "rnb_modern": {"skeleton_strength": 0.55, "backbeat_variation": 0.45, "ornament_amount": 0.80},
    "country_train": {"skeleton_strength": 0.85, "backbeat_variation": 0.20, "ornament_amount": 0.30},
    "two_beat_country": {"skeleton_strength": 0.80, "backbeat_variation": 0.25, "ornament_amount": 0.25},
    "classic_funk": {"skeleton_strength": 0.65, "backbeat_variation": 0.35, "ornament_amount": 0.70},
    "syncopated_funk": {"skeleton_strength": 0.50, "backbeat_variation": 0.50, "ornament_amount": 0.85},
    "one_drop": {"skeleton_strength": 0.90, "backbeat_variation": 0.10, "ornament_amount": 0.25},
    "rockers": {"skeleton_strength": 0.80, "backbeat_variation": 0.20, "ornament_amount": 0.40},
    "ska_offbeat": {"skeleton_strength": 0.70, "backbeat_variation": 0.30, "ornament_amount": 0.60},
}


def grooves_for_style(style: str) -> tuple[str, ...]:
    return GROOVES_BY_STYLE.get(style, ("free",))


def default_groove(style: str) -> str:
    return DEFAULT_GROOVE_BY_STYLE.get(style, "free")

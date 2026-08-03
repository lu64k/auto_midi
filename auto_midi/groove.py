"""Named groove templates used to keep style identity stable."""

from __future__ import annotations


GROOVES_BY_STYLE = {
    "free": ("free",),
    "boom_bap": ("boom_bap",),
    "hiphop": ("hiphop",),
    "trap": ("trap",),
    "minimal": ("minimal",),
    "rock": ("classic_rock", "driving_rock", "half_time_rock"),
    "jazz": ("swing_ride", "jazz_waltz"),
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
    "swing_ride": "floating",
    "jazz_waltz": "floating",
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
    "boom_bap": 8,
    "hiphop": 8,
    "trap": 16,
    "minimal": 8,
    "swing_ride": 8,
    "jazz_waltz": 8,
    "country_train": 8,
    "two_beat_country": 8,
    "classic_funk": 16,
    "syncopated_funk": 16,
    "one_drop": 8,
    "rockers": 8,
    "ska_offbeat": 8,
}


def grooves_for_style(style: str) -> tuple[str, ...]:
    return GROOVES_BY_STYLE.get(style, ("free",))


def default_groove(style: str) -> str:
    return DEFAULT_GROOVE_BY_STYLE.get(style, "free")

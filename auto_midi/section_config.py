"""Explicit song-section controls for the drum event generator."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .drum_rack import GENERAL_MIDI_DRUMS
from .groove import GROOVE_PROFILES


FILL_MODES = ("none", "every_4", "last_bar", "last_2_bars", "section_end")
VOICE_PLACEMENTS = (
    "auto", "section_start", "section_end", "first_bar", "last_bar",
    "every_bar", "phrase_start", "phrase_end",
)
CYMBAL_ROLES = (
    "none", "closed_hat_quarters", "closed_hat_eighths",
    "open_hat_quarters", "ride_quarters", "ride_eighths",
    "ride_bell_offbeats",
)

VOICE_ALIASES = {
    "bass_drum": "kick",
    "kick_drum": "kick",
    "side_stick": "rim",
    "rimshot": "rim",
    "tom": "mid_tom",
    "tom_tom": "mid_tom",
    "floor_tom": "low_tom",
    "hi_hat": "closed_hat",
    "hihat": "closed_hat",
    "hat": "closed_hat",
    "closed_hi_hat": "closed_hat",
    "closed_hihat": "closed_hat",
    "open_hi_hat": "open_hat",
    "open_hihat": "open_hat",
    "crash_cymbal": "crash",
    "ride_cymbal": "ride",
}


@dataclass(frozen=True)
class SectionConfig:
    """Per-section controls layered on top of one generated DrummerDNA."""

    name: str
    bars: int
    intensity_start: int | None = None
    intensity_end: int | None = None
    density_start: float | None = None
    density_end: float | None = None
    fill: int | None = None
    fill_mode: str = "section_end"
    allowed_voices: tuple[str, ...] | None = None
    required_voices: tuple[str, ...] = ()
    voice_placements: dict[str, str] = field(default_factory=dict)
    groove: str | None = None
    cymbal_role: str | None = None
    intensity_curve: tuple[tuple[int, float], ...] = ()
    density_curve: tuple[tuple[int, float], ...] = ()
    dna_overrides: dict[str, Any] = field(default_factory=dict)
    section_type: str | None = None
    chord_bars: tuple[tuple[str, ...], ...] = ()
    repeat_of: str | None = None


def load_section_config(path: Path) -> tuple[SectionConfig, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_section_config(payload)


def parse_section_config(payload: Any) -> tuple[SectionConfig, ...]:
    """Parse a JSON-compatible execution config object."""

    raw_sections = payload.get("sections") if isinstance(payload, dict) else payload
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("section config must contain a non-empty 'sections' list")

    sections: list[SectionConfig] = []
    for index, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            raise ValueError(f"section {index} must be an object")
        section = SectionConfig(
            name=str(raw.get("name", f"section_{index + 1}")),
            bars=int(raw["bars"]),
            intensity_start=_optional_int(raw.get("intensity_start"), "intensity_start", index),
            intensity_end=_optional_int(raw.get("intensity_end"), "intensity_end", index),
            density_start=_optional_float(raw.get("density_start"), "density_start", index),
            density_end=_optional_float(raw.get("density_end"), "density_end", index),
            fill=_optional_int(raw.get("fill"), "fill", index),
            fill_mode=str(raw.get("fill_mode", "section_end")),
            allowed_voices=_optional_voices(raw.get("allowed"), index),
            required_voices=_optional_voices(raw.get("required"), index) or (),
            voice_placements=_voice_placements(raw.get("voice_placements", {}), index),
            groove=_optional_text(raw.get("groove")),
            cymbal_role=_optional_text(raw.get("cymbal_role")),
            intensity_curve=_curve(raw.get("intensity_curve", []), "intensity_curve", index),
            density_curve=_curve(raw.get("density_curve", []), "density_curve", index),
            dna_overrides=dict(raw.get("dna_overrides", {})),
            section_type=_optional_text(raw.get("type")),
            chord_bars=_optional_chord_bars(raw.get("chord_bars", raw.get("chords", [])), index),
            repeat_of=_optional_text(raw.get("repeat_of")),
        )
        if section.bars <= 0:
            raise ValueError(f"section {index} bars must be positive")
        _check_range(section.intensity_start, 0, 100, "intensity_start", index)
        _check_range(section.intensity_end, 0, 100, "intensity_end", index)
        _check_range(section.density_start, 0.0, 1.0, "density_start", index)
        _check_range(section.density_end, 0.0, 1.0, "density_end", index)
        _check_range(section.fill, 0, 100, "fill", index)
        if section.fill_mode not in FILL_MODES:
            raise ValueError(f"section {index} fill_mode must be one of {FILL_MODES}")
        if section.groove is not None and section.groove not in GROOVE_PROFILES:
            raise ValueError(f"section {index} contains unknown groove: {section.groove}")
        if section.cymbal_role is not None and section.cymbal_role not in CYMBAL_ROLES:
            raise ValueError(f"section {index} cymbal_role must be one of {CYMBAL_ROLES}")
        if section.allowed_voices and not set(section.required_voices).issubset(section.allowed_voices):
            raise ValueError(f"section {index} required voices must be included in allowed voices")
        if section.allowed_voices and not set(section.voice_placements).issubset(section.allowed_voices):
            raise ValueError(f"section {index} placed voices must be included in allowed voices")
        _validate_curve(section.intensity_curve, section.bars, 0, 100, "intensity_curve", index)
        _validate_curve(section.density_curve, section.bars, 0.0, 1.0, "density_curve", index)
        sections.append(section)
    return tuple(sections)


def _optional_int(value: Any, field_name: str, index: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"section {index} {field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"section {index} {field_name} must be an integer") from exc


def _optional_voices(value: Any, index: int) -> tuple[str, ...] | None:
    if value is None or value == []:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"section {index} allowed must be a list of non-empty voice names")
    normalized = []
    for item in value:
        voice = item.strip().lower().replace("-", "_").replace(" ", "_")
        normalized.append(VOICE_ALIASES.get(voice, voice))
    voices = tuple(dict.fromkeys(normalized))
    unknown = sorted(set(voices) - set(GENERAL_MIDI_DRUMS))
    if unknown:
        raise ValueError(f"section {index} contains unknown drum voices: {', '.join(unknown)}")
    return voices


def _voice_placements(value: Any, index: int) -> dict[str, str]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"section {index} voice_placements must be an object")
    result: dict[str, str] = {}
    for raw_voice, raw_placement in value.items():
        voices = _optional_voices([raw_voice], index)
        voice = voices[0] if voices else ""
        placement = str(raw_placement).strip().lower()
        if placement not in VOICE_PLACEMENTS:
            raise ValueError(f"section {index} voice placement must be one of {VOICE_PLACEMENTS}")
        result[voice] = placement
    return result


def _curve(value: Any, field_name: str, index: int) -> tuple[tuple[int, float], ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list):
        raise ValueError(f"section {index} {field_name} must be a list")
    points = []
    for point in value:
        if not isinstance(point, dict) or "bar" not in point or "value" not in point:
            raise ValueError(f"section {index} {field_name} points need bar and value")
        points.append((int(point["bar"]), float(point["value"])))
    return tuple(points)


def _validate_curve(
    curve: tuple[tuple[int, float], ...], bars: int, low: float, high: float,
    field_name: str, index: int,
) -> None:
    if not curve:
        return
    curve_bars = [bar for bar, _ in curve]
    if curve_bars != sorted(set(curve_bars)):
        raise ValueError(f"section {index} {field_name} bars must be unique and ascending")
    if any(bar < 1 or bar > bars for bar in curve_bars):
        raise ValueError(f"section {index} {field_name} bar must be within the section")
    if any(value < low or value > high for _, value in curve):
        raise ValueError(f"section {index} {field_name} values must be between {low} and {high}")


def _optional_chord_bars(value: Any, index: int) -> tuple[tuple[str, ...], ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list):
        raise ValueError(f"section {index} chords must be a list")
    if all(isinstance(item, str) for item in value):
        return tuple((item.strip(),) for item in value if item.strip())
    result: list[tuple[str, ...]] = []
    for bar_index, bar_chords in enumerate(value, start=1):
        if isinstance(bar_chords, str):
            bar_chords = [bar_chords]
        if not isinstance(bar_chords, list) or not bar_chords:
            raise ValueError(f"section {index} chord bar {bar_index} must be a non-empty list")
        if not all(isinstance(chord, str) and chord.strip() for chord in bar_chords):
            raise ValueError(f"section {index} chord bar {bar_index} contains an invalid chord")
        result.append(tuple(chord.strip() for chord in bar_chords))
    return tuple(result)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any, field_name: str, index: int) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"section {index} {field_name} must be a number") from exc


def _check_range(value: Any, low: float, high: float, field_name: str, index: int) -> None:
    if value is not None and not low <= value <= high:
        raise ValueError(f"section {index} {field_name} must be between {low} and {high}")

"""Explicit song-section controls for the drum event generator."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .drum_rack import GENERAL_MIDI_DRUMS


FILL_MODES = ("none", "every_4", "last_bar", "last_2_bars", "section_end")


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
    dna_overrides: dict[str, Any] = field(default_factory=dict)
    section_type: str | None = None
    chord_bars: tuple[tuple[str, ...], ...] = ()
    repeat_of: str | None = None


def load_section_config(path: Path) -> tuple[SectionConfig, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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
        if section.allowed_voices and not set(section.required_voices).issubset(section.allowed_voices):
            raise ValueError(f"section {index} required voices must be included in allowed voices")
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
    voices = tuple(dict.fromkeys(item.strip() for item in value))
    unknown = sorted(set(voices) - set(GENERAL_MIDI_DRUMS))
    if unknown:
        raise ValueError(f"section {index} contains unknown drum voices: {', '.join(unknown)}")
    return voices


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

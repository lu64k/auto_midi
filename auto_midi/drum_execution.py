"""Compile structured drum feels into the existing execution configuration."""

from __future__ import annotations

from dataclasses import replace

from .drum_feel import DrumFeel
from .section_config import SectionConfig
from .song_structure import SongStructure, resolved_chord_bars


def compile_execution_config(
    structure: SongStructure,
    feels: tuple[DrumFeel, ...],
) -> tuple[SectionConfig, ...]:
    """Convert one feel per authored section into executable section configs."""

    if len(feels) != len(structure.sections):
        raise ValueError(
            f"drum feels contain {len(feels)} sections, expected {len(structure.sections)}"
        )
    expected_ids = [section.id for section in structure.sections]
    actual_ids = [feel.section_id for feel in feels]
    if actual_ids != expected_ids:
        raise ValueError("drum feel section order/ids do not match song structure")

    result: list[SectionConfig] = []
    for section, feel in zip(structure.sections, feels):
        result.append(
            SectionConfig(
                name=section.id,
                bars=section.bars,
                intensity_start=_percent(feel.energy - 0.04),
                intensity_end=_percent(feel.energy + 0.04),
                density_start=_clamp(feel.density - 0.04),
                density_end=_clamp(feel.density + 0.04),
                fill=_percent(feel.fill_level),
                fill_mode=_fill_mode(section.bars, feel.fill_level),
                allowed_voices=feel.allowed_voices,
                required_voices=feel.required_voices,
                section_type=section.type,
                chord_bars=resolved_chord_bars(structure, section.id),
                repeat_of=section.repeat_of,
                dna_overrides={
                    "backbeat_weight": _clamp(feel.backbeat_strength),
                    "syncopation": _clamp(feel.syncopation),
                    "swing": _clamp(feel.swing),
                    "mutation": _clamp(feel.variation),
                },
            )
        )
    return tuple(result)


def _percent(value: float) -> int:
    return int(round(_clamp(value) * 100))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _fill_mode(bars: int, fill_level: float) -> str:
    if fill_level <= 0.02:
        return "none"
    if bars >= 8 and fill_level >= 0.16:
        return "every_4"
    return "section_end"

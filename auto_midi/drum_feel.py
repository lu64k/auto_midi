"""Structured drum-feel generation for authored song sections.

The first implementation is a deterministic local agent.  It establishes the
same input/output contract that a future LLM-backed agent will implement, so
the rest of the pipeline does not depend on a particular model provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import random
from typing import Any, Protocol

from .groove import GROOVE_PROFILES, default_groove, grooves_for_style
from .song_structure import SongStructure, resolved_chord_bars


@dataclass(frozen=True)
class DrumFeel:
    section_id: str
    section_type: str
    groove: str
    description: str
    energy: float
    density: float
    backbeat_strength: float
    syncopation: float
    swing: float
    variation: float
    fill_level: float
    crash_usage: str
    dropout: float
    chord_context: tuple[tuple[str, ...], ...] = ()
    allowed_voices: tuple[str, ...] | None = None
    required_voices: tuple[str, ...] = ()
    source: str = "rule"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DrumFeelAgent(Protocol):
    def generate(self, structure: SongStructure, preset: str, groove: str | None, seed: int) -> tuple[DrumFeel, ...]:
        """Generate one structured feel per authored song section."""


class RuleBasedDrumFeelAgent:
    """Safe local fallback with style-aware section dynamics.

    It never invents chord context: sections without chords keep an empty
    ``chord_context`` tuple.  Randomness only adds bounded variation around
    section defaults and is repeatable for a fixed seed.
    """

    def generate(self, structure: SongStructure, preset: str, groove: str | None, seed: int) -> tuple[DrumFeel, ...]:
        rng = random.Random(seed)
        result: list[DrumFeel] = []
        previous_energy = 0.0
        for index, section in enumerate(structure.sections):
            selected_groove = groove if groove in grooves_for_style(preset) else default_groove(preset)
            chord_context = resolved_chord_bars(structure, section.id)
            base = _section_defaults(section.type)
            profile = GROOVE_PROFILES.get(selected_groove, GROOVE_PROFILES["free"])
            next_type = structure.sections[index + 1].type if index + 1 < len(structure.sections) else None
            energy = _bounded(base["energy"] + _transition_delta(section.type, next_type, previous_energy), rng, 0.08)
            density = _bounded(base["density"] + (energy - base["energy"]) * 0.25, rng, 0.06)
            backbeat = _bounded(base["backbeat"] * 0.55 + profile["skeleton_strength"] * 0.45, rng, 0.05)
            syncopation = _bounded(base["syncopation"] + profile["backbeat_variation"] * 0.15, rng, 0.06)
            swing = _bounded(base["swing"], rng, 0.03)
            variation = _bounded(base["variation"] + profile["backbeat_variation"] * 0.15, rng, 0.05)
            fill_level = _bounded(base["fill"] + profile["ornament_amount"] * 0.08, rng, 0.04)
            dropout = _bounded(base["dropout"], rng, 0.03)
            result.append(
                DrumFeel(
                    section_id=section.id,
                    section_type=section.type,
                    groove=selected_groove,
                    description=_description(section.type, selected_groove, chord_context),
                    energy=energy,
                    density=density,
                    backbeat_strength=backbeat,
                    syncopation=syncopation,
                    swing=swing,
                    variation=variation,
                    fill_level=fill_level,
                    crash_usage=_crash_usage(section.type),
                    dropout=dropout,
                    chord_context=chord_context,
                    source="rule",
                )
            )
            previous_energy = energy
        return tuple(result)


def _section_defaults(section_type: str) -> dict[str, float]:
    return {
        "energy": {"intro": 0.2, "verse": 0.4, "pre_chorus": 0.58, "chorus": 0.78, "bridge": 0.5, "instrumental": 0.62, "outro": 0.38}.get(section_type, 0.45),
        "density": {"intro": 0.16, "verse": 0.36, "pre_chorus": 0.5, "chorus": 0.68, "bridge": 0.42, "instrumental": 0.58, "outro": 0.28}.get(section_type, 0.4),
        "backbeat": {"intro": 0.3, "verse": 0.7, "pre_chorus": 0.78, "chorus": 0.9, "bridge": 0.55, "instrumental": 0.72, "outro": 0.45}.get(section_type, 0.6),
        "syncopation": {"intro": 0.1, "verse": 0.2, "pre_chorus": 0.25, "chorus": 0.22, "bridge": 0.42, "instrumental": 0.35, "outro": 0.12}.get(section_type, 0.25),
        "swing": 0.0,
        "variation": {"intro": 0.08, "verse": 0.16, "pre_chorus": 0.2, "chorus": 0.24, "bridge": 0.3, "instrumental": 0.3, "outro": 0.12}.get(section_type, 0.18),
        "fill": {"intro": 0.02, "verse": 0.08, "pre_chorus": 0.16, "chorus": 0.2, "bridge": 0.18, "instrumental": 0.2, "outro": 0.05}.get(section_type, 0.1),
        "dropout": {"intro": 0.15, "verse": 0.06, "pre_chorus": 0.03, "chorus": 0.02, "bridge": 0.1, "instrumental": 0.04, "outro": 0.25}.get(section_type, 0.08),
    }


def _transition_delta(section_type: str, next_type: str | None, previous_energy: float) -> float:
    delta = 0.0
    if section_type == "pre_chorus":
        delta += 0.06
    if next_type == "chorus":
        delta += 0.04
    if section_type == "outro":
        delta -= 0.04
    if previous_energy and section_type == "verse":
        delta -= 0.02
    return delta


def _bounded(value: float, rng: random.Random, spread: float) -> float:
    return max(0.0, min(1.0, value + rng.uniform(-spread, spread)))


def _crash_usage(section_type: str) -> str:
    return {
        "intro": "section_entry_only",
        "verse": "section_entry_only",
        "pre_chorus": "transition_only",
        "chorus": "section_entry_and_major_accents",
        "bridge": "transition_only",
        "instrumental": "accent_only",
        "outro": "none_or_final_hit",
    }.get(section_type, "accent_only")


def _description(section_type: str, groove: str, chords: tuple[tuple[str, ...], ...]) -> str:
    chord_note = "，使用当前段落和弦变化作为重音参考" if chords else "，不使用和弦上下文"
    return f"{section_type} 使用 {groove} 骨架，按段落能量控制密度和过门{chord_note}"

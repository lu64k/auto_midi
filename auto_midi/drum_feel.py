"""Structured drum-feel generation for authored song sections.

The first implementation is a deterministic local agent.  It establishes the
same input/output contract that a future LLM-backed agent will implement, so
the rest of the pipeline does not depend on a particular model provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
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


def parse_drum_feels(
    payload: Any,
    structure: SongStructure,
    source: str = "user_edit",
) -> tuple[DrumFeel, ...]:
    """Parse user-edited feel JSON and enforce authored section order."""

    if isinstance(payload, dict):
        payload = payload.get("sections", payload.get("feels"))
    if not isinstance(payload, list):
        raise ValueError("drum feel JSON must contain a sections list")
    if len(payload) != len(structure.sections):
        raise ValueError(
            f"drum feel JSON contains {len(payload)} sections, expected {len(structure.sections)}"
        )

    feels: list[DrumFeel] = []
    for section, raw in zip(structure.sections, payload):
        if not isinstance(raw, dict):
            raise ValueError(f"drum feel for {section.id} must be an object")
        if str(raw.get("section_id", "")).strip() != section.id:
            raise ValueError(f"drum feel section id must be {section.id!r}")
        feels.append(
            DrumFeel(
                section_id=section.id,
                section_type=str(raw.get("section_type", section.type)),
                groove=str(raw.get("groove", "free")),
                description=str(raw.get("description", "")).strip(),
                energy=_feel_number(raw.get("energy"), section.id, "energy"),
                density=_feel_number(raw.get("density"), section.id, "density"),
                backbeat_strength=_feel_number(raw.get("backbeat_strength"), section.id, "backbeat_strength"),
                syncopation=_feel_number(raw.get("syncopation"), section.id, "syncopation"),
                swing=_feel_number(raw.get("swing"), section.id, "swing"),
                variation=_feel_number(raw.get("variation"), section.id, "variation"),
                fill_level=_feel_number(raw.get("fill_level"), section.id, "fill_level"),
                crash_usage=str(raw.get("crash_usage", "accent_only")),
                dropout=_feel_number(raw.get("dropout"), section.id, "dropout"),
                chord_context=tuple(tuple(str(chord) for chord in bar) for bar in raw.get("chord_context", [])),
                allowed_voices=_optional_voice_tuple(raw.get("allowed_voices")),
                required_voices=tuple(str(voice) for voice in raw.get("required_voices", [])),
                source=source,
            )
        )
    return tuple(feels)


def _feel_number(value: Any, section_id: str, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"drum feel {section_id} {field_name} must be a number") from exc
    if not 0.0 <= parsed <= 1.0:
        raise ValueError(f"drum feel {section_id} {field_name} must be between 0 and 1")
    return parsed


def _optional_voice_tuple(value: Any) -> tuple[str, ...] | None:
    if value in (None, []):
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError("drum feel allowed_voices must be a list of non-empty names")
    return tuple(dict.fromkeys(item.strip() for item in value))


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


class LLMDrumFeelAgent:
    """OpenAI-compatible model-backed feel agent with strict JSON validation."""

    def __init__(self, client):
        self.client = client

    def generate(self, structure: SongStructure, preset: str, groove: str | None, seed: int) -> tuple[DrumFeel, ...]:
        context = {
            "title": structure.title,
            "bpm": structure.bpm,
            "time_signature": structure.time_signature,
            "key": structure.key,
            "preset": preset,
            "groove": groove,
            "sections": [
                {
                    "id": section.id,
                    "type": section.type,
                    "index": section.index,
                    "bars": section.bars,
                    "chords": [list(bar) for bar in resolved_chord_bars(structure, section.id)],
                    "repeat_of": section.repeat_of,
                }
                for section in structure.sections
            ],
        }
        payload = self.client.complete_json(_SYSTEM_PROMPT, json.dumps(context, ensure_ascii=False), seed)
        return parse_drum_feels(payload, structure, source="llm")


def build_drum_feel_agent():
    """Use the configured gateway when a key exists, otherwise use local rules."""

    from .llm_client import OpenAICompatibleClient
    from .settings import settings

    api_key = settings.llm_api_key()
    if settings.llm_enabled and api_key:
        return LLMDrumFeelAgent(
            OpenAICompatibleClient(
                base_url=settings.llm_base_url,
                api_key=api_key,
                model=settings.llm_model,
                timeout=settings.llm_timeout,
            )
        )
    return RuleBasedDrumFeelAgent()


_SYSTEM_PROMPT = """You are a drum-arrangement agent. Return JSON only.
Create exactly one feel object for every input section, in the same order and
with the same section_id. Do not invent chords: chord_context must be empty
when the input section has no chords. Use values from 0 to 1 for every numeric
feel field. allowed_voices=[] or null means all drum voices are allowed;
required_voices is only for voices that must occur. Prefer existing groove
names. The output root must be {\"sections\": [...]}. Each object must contain:
section_id, section_type, groove, description, energy, density,
backbeat_strength, syncopation, swing, variation, fill_level, crash_usage,
dropout, chord_context, allowed_voices, required_voices.
"""


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

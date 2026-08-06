"""Structured drum-feel generation for authored song sections.

The first implementation is a deterministic local agent.  It establishes the
same input/output contract that a future LLM-backed agent will implement, so
the rest of the pipeline does not depend on a particular model provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import random
import re
from typing import Any, Protocol

from .groove import GROOVE_PROFILES, default_groove, grooves_for_style
from .song_structure import SongStructure, parse_song_structure, resolved_chord_bars


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
    role_in_song: str = ""
    relationship_to_previous: str = ""
    relationship_to_next: str = ""
    groove_character: str = ""
    kick_feel: str = ""
    snare_feel: str = ""
    cymbal_feel: str = ""
    dynamics_arc: str = ""
    fill_and_transition: str = ""
    chord_and_lyric_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_plan_dict(self) -> dict[str, Any]:
        """Serialize only the semantic plan authored by the first Agent."""

        return {
            "section_id": self.section_id,
            "section_type": self.section_type,
            "groove": self.groove,
            "description": self.description,
            "role_in_song": self.role_in_song,
            "relationship_to_previous": self.relationship_to_previous,
            "relationship_to_next": self.relationship_to_next,
            "groove_character": self.groove_character,
            "kick_feel": self.kick_feel,
            "snare_feel": self.snare_feel,
            "cymbal_feel": self.cymbal_feel,
            "dynamics_arc": self.dynamics_arc,
            "fill_and_transition": self.fill_and_transition,
            "chord_and_lyric_response": self.chord_and_lyric_response,
            "chord_context": [list(bar) for bar in self.chord_context],
            "allowed_voices": list(self.allowed_voices) if self.allowed_voices is not None else [],
            "required_voices": list(self.required_voices),
        }


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
        defaults = _section_defaults(section.type)
        feels.append(
            DrumFeel(
                section_id=section.id,
                section_type=str(raw.get("section_type", section.type)),
                groove=str(raw.get("groove", "free")),
                description=str(raw.get("description", "")).strip(),
                energy=_feel_number(raw.get("energy", defaults["energy"]), section.id, "energy"),
                density=_feel_number(raw.get("density", defaults["density"]), section.id, "density"),
                backbeat_strength=_feel_number(raw.get("backbeat_strength", defaults["backbeat"]), section.id, "backbeat_strength"),
                syncopation=_feel_number(raw.get("syncopation", defaults["syncopation"]), section.id, "syncopation"),
                swing=_feel_number(raw.get("swing", defaults["swing"]), section.id, "swing"),
                variation=_feel_number(raw.get("variation", defaults["variation"]), section.id, "variation"),
                fill_level=_feel_number(raw.get("fill_level", defaults["fill"]), section.id, "fill_level"),
                crash_usage=str(raw.get("crash_usage", "accent_only")),
                dropout=_feel_number(raw.get("dropout", defaults["dropout"]), section.id, "dropout"),
                chord_context=_parse_chord_context(raw.get("chord_context", [])),
                allowed_voices=_optional_voice_tuple(raw.get("allowed_voices")),
                required_voices=tuple(str(voice) for voice in raw.get("required_voices", [])),
                source=source,
                role_in_song=str(raw.get("role_in_song", "")).strip(),
                relationship_to_previous=str(raw.get("relationship_to_previous", "")).strip(),
                relationship_to_next=str(raw.get("relationship_to_next", "")).strip(),
                groove_character=str(raw.get("groove_character", "")).strip(),
                kick_feel=str(raw.get("kick_feel", "")).strip(),
                snare_feel=str(raw.get("snare_feel", "")).strip(),
                cymbal_feel=str(raw.get("cymbal_feel", "")).strip(),
                dynamics_arc=str(raw.get("dynamics_arc", "")).strip(),
                fill_and_transition=str(raw.get("fill_and_transition", "")).strip(),
                chord_and_lyric_response=str(raw.get("chord_and_lyric_response", "")).strip(),
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


def _parse_chord_context(value: Any) -> tuple[tuple[str, ...], ...]:
    """Accept flat or per-bar chord arrays without splitting chord strings."""

    if value in (None, []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("drum feel chord_context must be a list")
    result = []
    for bar in value:
        if isinstance(bar, str):
            chord = bar.strip()
            if not chord:
                raise ValueError("drum feel chord_context contains an empty chord")
            result.append((chord,))
            continue
        if not isinstance(bar, (list, tuple)) or not bar:
            raise ValueError("drum feel chord_context bar must be a chord string or non-empty list")
        chords = tuple(str(chord).strip() for chord in bar)
        if any(not chord for chord in chords):
            raise ValueError("drum feel chord_context contains an empty chord")
        result.append(chords)
    return tuple(result)


class DrumFeelAgent(Protocol):
    def generate(self, structure: SongStructure, preset: str, groove: str | None, seed: int, requirements: str | None = None) -> tuple[DrumFeel, ...]:
        """Generate one structured feel per authored song section."""


class RuleBasedDrumFeelAgent:
    """Safe local fallback with style-aware section dynamics.

    It never invents chord context: sections without chords keep an empty
    ``chord_context`` tuple.  Randomness only adds bounded variation around
    section defaults and is repeatable for a fixed seed.
    """

    def generate(self, structure: SongStructure, preset: str, groove: str | None, seed: int, requirements: str | None = None) -> tuple[DrumFeel, ...]:
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

    def generate_raw_plan(
        self,
        requirements: str,
        bpm: int,
        time_signature: str,
        preset: str,
        groove: str | None,
        seed: int,
    ) -> dict[str, Any]:
        """Return the first Agent JSON exactly as produced by the model."""

        return self.client.complete_json(
            _REQUIREMENTS_SYSTEM_PROMPT,
            json.dumps(
                {
                    "requirements": requirements,
                    "bpm_default": bpm,
                    "time_signature_default": time_signature,
                    "preset": preset,
                    "groove": groove,
                },
                ensure_ascii=False,
            ),
            seed,
        )

    def generate_from_requirements(
        self,
        requirements: str,
        bpm: int,
        time_signature: str,
        preset: str,
        groove: str | None,
        seed: int,
    ) -> tuple[SongStructure, tuple[DrumFeel, ...]]:
        payload = self.generate_raw_plan(requirements, bpm, time_signature, preset, groove, seed)
        structure = normalize_plan_structure(payload, requirements)
        raw_feels = payload.get("feels", payload.get("sections"))
        if not isinstance(raw_feels, list):
            raise ValueError("feel plan must contain a feels list")
        defaults = {
            feel.section_id: feel.to_dict()
            for feel in RuleBasedDrumFeelAgent().generate(structure, preset, groove, seed)
        }
        normalized_feels = []
        for position, section in enumerate(structure.sections):
            raw_feel = raw_feels[position] if position < len(raw_feels) and isinstance(raw_feels[position], dict) else {}
            merged = dict(defaults[section.id])
            merged.update({key: value for key, value in raw_feel.items() if value not in (None, "")})
            merged["section_id"] = section.id
            merged["section_type"] = section.type
            normalized_feels.append(merged)
        feels = parse_drum_feels(normalized_feels, structure, source="llm")
        return structure, feels

    def generate(self, structure: SongStructure, preset: str, groove: str | None, seed: int, requirements: str | None = None) -> tuple[DrumFeel, ...]:
        context = {
            "natural_language_requirements": requirements or "",
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


def normalize_plan_structure(payload: dict[str, Any], requirements: str) -> SongStructure:
    """Build hidden program state without altering the first Agent payload."""

    raw_structure = dict(payload.get("structure", payload))
    raw_sections = raw_structure.get("sections", [])
    authored_progressions = _extract_authored_chord_progressions(requirements)
    cursor = 1
    normalized_sections = []
    for position, raw_section in enumerate(raw_sections, start=1):
        section = dict(raw_section)
        try:
            bars = int(section.get("bars") or 1)
        except (TypeError, ValueError):
            bars = 1
        start = section.get("lyrics_start")
        end = section.get("lyrics_end")
        if not isinstance(start, int) or start < 1:
            start = cursor
        if not isinstance(end, int) or end < start:
            end = start + bars - 1
        section["id"] = str(section.get("id") or f"section_{position}")
        section["index"] = position
        section["bars"] = bars
        section["lyrics_start"] = start
        section["lyrics_end"] = end
        chords = section.get("chords", section.get("chord_bars", []))
        if isinstance(chords, list) and chords:
            chord_symbols = [str(item[0] if isinstance(item, list) and item else item).strip() for item in chords]
            for progression in authored_progressions:
                flattened = [part for chord in progression for part in chord.split("/")]
                if chord_symbols[: len(progression)] == list(progression) or chord_symbols[: len(flattened)] == flattened:
                    chords = list(progression)
                    break
            chords = [chords[index % len(chords)] for index in range(bars)]
        else:
            chords = []
        section["chords"] = chords
        normalized_sections.append(section)
        cursor = end + 1
    raw_structure["sections"] = normalized_sections
    return parse_song_structure(raw_structure)


_CHORD_TOKEN = r"[A-G](?:#|b)?(?:maj|min|m|dim|aug|sus|add)?\d*(?:/[A-G](?:#|b)?)?"
_CHORD_PROGRESSION_RE = re.compile(rf"(?<![A-Za-z0-9#/])({_CHORD_TOKEN}(?:\s*-\s*{_CHORD_TOKEN})+)")


def _extract_authored_chord_progressions(text: str) -> tuple[tuple[str, ...], ...]:
    """Extract hyphen-separated progressions while preserving slash chords."""

    progressions = []
    for match in _CHORD_PROGRESSION_RE.finditer(text):
        chords = tuple(part.strip() for part in re.split(r"\s*-\s*", match.group(1)))
        if chords:
            progressions.append(chords)
    return tuple(progressions)


_REQUIREMENTS_SYSTEM_PROMPT = """You are a song-level drum-feel planning agent. Return JSON only.
Read the complete natural-language lyrics and production requirements. Infer
every requested song section (intro, verse, pre_chorus, chorus, bridge,
instrumental, outro, etc.) and its bar count. Use the lyrics, chord movement,
section function, and emotional character to decide the drum contour of every
section. Do not collapse the song into one verse.

This stage is a musical direction brief, not an execution config. Do not output
numeric values for energy, density, swing, syncopation, variation, fill level,
probability, velocity, or any other implementation parameter. The next agent
will translate your musical descriptions into executable numbers.

Return exactly {"structure": {...}, "feels": [...]}. The structure must have
title, bpm, time_signature, key, and sections. Each structure section needs id,
type, index, bars, lyrics_start, lyrics_end, chords, repeat_of. Chords must be
per-section and may be [] when the user did not provide them. Preserve chord
symbols exactly as authored. A slash chord such as C/G is one atomic chord and
must never be split into C and G. A hyphen between chord symbols separates the
progression: C/G-E-A-Fm means exactly ["C/G", "E", "A", "Fm"].

Create exactly one unique feel plan for every structure section, in the same
order and with the same section_id. Never reuse identical descriptions across
sections. Every feel plan must explain how the section enters from the previous
section, develops internally, and hands off to the next section. It must contain:
section_id, section_type, groove, description, role_in_song,
relationship_to_previous, relationship_to_next, groove_character, kick_feel,
snare_feel, cymbal_feel, dynamics_arc, fill_and_transition,
chord_and_lyric_response, chord_context, allowed_voices, required_voices.

description must be a concrete, section-specific summary rather than a generic
genre label. relationship_to_previous and relationship_to_next must reference
the actual neighboring section ids, or state that there is no neighbor at the
song boundary. Describe musical gestures in natural language: pulse placement,
space, accents, orchestration, buildup, release, dropouts, and transitions.
allowed_voices=[] or null means all drum voices are allowed. required_voices
contains only instruments that must occur. Return no Markdown fences.
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

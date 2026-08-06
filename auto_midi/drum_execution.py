"""Compile structured drum feels into the existing execution configuration."""

from __future__ import annotations

from dataclasses import replace
import json

from .drum_feel import DrumFeel
from .groove import GROOVE_PROFILES
from .section_config import SectionConfig, parse_section_config
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
                groove=feel.groove if feel.groove in GROOVE_PROFILES else None,
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


def execution_config_payload(configs: tuple[SectionConfig, ...]) -> dict:
    """Serialize execution configs for CLI/Gradio inspection or editing."""

    return {
        "sections": [
            {
                "name": config.name,
                "type": config.section_type,
                "bars": config.bars,
                "intensity_start": config.intensity_start,
                "intensity_end": config.intensity_end,
                "density_start": config.density_start,
                "density_end": config.density_end,
                "fill": config.fill,
                "fill_mode": config.fill_mode,
                "allowed": list(config.allowed_voices or []),
                "required": list(config.required_voices),
                "voice_placements": config.voice_placements,
                "groove": config.groove,
                "cymbal_role": config.cymbal_role,
                "intensity_curve": [{"bar": bar, "value": value} for bar, value in config.intensity_curve],
                "density_curve": [{"bar": bar, "value": value} for bar, value in config.density_curve],
                "chord_bars": [list(bar) for bar in config.chord_bars],
                "dna_overrides": config.dna_overrides,
            }
            for config in configs
        ]
    }


class RuleBasedDrumExecutionAgent:
    def generate(self, structure: SongStructure, feels: tuple[DrumFeel, ...], seed: int) -> tuple[SectionConfig, ...]:
        return compile_execution_config(structure, feels)


class LLMDrumExecutionAgent:
    """OpenAI-compatible compiler from validated drum feelings to drum config."""

    def __init__(self, client):
        self.client = client

    def generate_from_plan_payload(self, plan_payload: dict, seed: int) -> tuple[SectionConfig, ...]:
        """Compile the first Agent payload without pre-parsing its feel fields."""

        payload = self.client.complete_json(_SYSTEM_PROMPT, json.dumps(plan_payload, ensure_ascii=False), seed)
        return parse_section_config(payload)

    def generate(self, structure: SongStructure, feels: tuple[DrumFeel, ...], seed: int) -> tuple[SectionConfig, ...]:
        context = {
            "song": {
                "title": structure.title,
                "bpm": structure.bpm,
                "time_signature": structure.time_signature,
                "key": structure.key,
            },
            "sections": [feel.to_plan_dict() for feel in feels],
        }
        payload = self.client.complete_json(_SYSTEM_PROMPT, json.dumps(context, ensure_ascii=False), seed)
        configs = parse_section_config(payload)
        if len(configs) != len(structure.sections):
            raise ValueError("LLM execution config section count does not match song structure")
        expected_ids = [section.id for section in structure.sections]
        actual_ids = [config.name for config in configs]
        if actual_ids != expected_ids:
            raise ValueError("LLM execution config section names/order do not match song structure")
        normalized = []
        for section, config in zip(structure.sections, configs):
            if config.bars != section.bars:
                raise ValueError(f"LLM execution config {section.id} bars do not match song structure")
            normalized.append(
                replace(
                    config,
                    section_type=section.type,
                    chord_bars=resolved_chord_bars(structure, section.id),
                    repeat_of=section.repeat_of,
                )
            )
        return tuple(normalized)


def build_drum_execution_agent():
    from .llm_client import OpenAICompatibleClient
    from .settings import settings

    api_key = settings.llm_api_key()
    if settings.llm_enabled and api_key:
        return LLMDrumExecutionAgent(
            OpenAICompatibleClient(
                base_url=settings.llm_base_url,
                api_key=api_key,
                model=settings.llm_model,
                timeout=settings.llm_timeout,
            )
        )
    return RuleBasedDrumExecutionAgent()


_SYSTEM_PROMPT = """You are a drum execution-config compiler. Return JSON only.
Convert each semantic section feeling into exactly one executable section.
Choose all implementation values from the musical descriptions, section
relationships, dynamics, instrument roles, and transition intent. Preserve
section name and bars exactly. Use fields: name, type, bars, intensity_start,
intensity_end (0-100), density_start, density_end (0-1), fill (0-100),
fill_mode (none/every_4/last_bar/last_2_bars/section_end), allowed (array or
empty array), required (array), voice_placements (object), groove, cymbal_role,
optional intensity_curve/density_curve arrays of {bar,value}, and dna_overrides.

Empty allowed means all voices are available. required means each listed voice
must occur at least once somewhere in the whole section; it never means once
per bar. required voices must be included in allowed when allowed is non-empty.
voice_placements may map a voice to auto, section_start, section_end, first_bar,
last_bar, every_bar, phrase_start, or phrase_end. Use section_end for a final
outro crash; use every_bar only when a hit on every bar is musically intended.

Use only valid drum voices: kick, rim, snare, clap, low_tom, mid_tom,
closed_hat, open_hat, crash, ride. Use these exact identifiers; write
closed_hat or open_hat, never hi-hat/hihat/hat.

Use only valid grooves: free, boom_bap, hiphop, trap, minimal, classic_rock,
driving_rock, half_time_rock, sparse_rock, shuffle_rock, blues_rock, punk_rock,
indie_rock, hard_rock, arena_rock, double_kick_rock, half_time_hard_rock,
sparse_dream, washed_8th, post_rock_build, post_rock_peak, post_rock_release,
psych_shuffle, psych_groove, motorik_rock, swing_ride, jazz_waltz,
blues_shuffle, slow_blues, rnb_soul, rnb_modern, country_train,
two_beat_country, classic_funk, syncopated_funk, one_drop, rockers,
ska_offbeat. Choose a section-specific groove from the semantic brief.

cymbal_role may be none, closed_hat_quarters, closed_hat_eighths,
open_hat_quarters, ride_quarters, ride_eighths, or ride_bell_offbeats. Use this
for a sustained Hat/Ride pattern; do not misuse required for a continuous
cymbal role. Curves override linear start/end values and are appropriate for
rise-then-fall sections. dna_overrides may use DrummerDNA fields such as
backbeat_weight, syncopation, swing, mutation, skeleton_strength,
backbeat_variation, ornament_amount, hat_openness, fill_vocabulary,
dynamic_shape, groove_anchor, pulse, low_bias, mid_bias, and high_density.
Do not put groove inside dna_overrides; use the top-level groove field.
Return {\"sections\": [...]}."""


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

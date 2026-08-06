"""Compile structured drum feels into the existing execution configuration."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json

from .drum_feel import DrumFeel
from .groove import GROOVE_PROFILES
from .groove_routing_skill import build_routing_skill_context, routing_catalog_metadata
from .section_config import SectionConfig, parse_section_config
from .song_structure import SongStructure, resolved_chord_bars
from .style_catalog import groove_owner, style_exists


@dataclass(frozen=True)
class ExecutionRouting:
    style: str
    global_groove: str
    style_source: str
    groove_source: str
    confidence: float
    reason: str
    section_override_reasons: dict[str, str]
    catalog_version: int
    catalog_hash: str

    def to_dict(self) -> dict:
        return {
            "style": self.style,
            "global_groove": self.global_groove,
            "style_source": self.style_source,
            "groove_source": self.groove_source,
            "confidence": self.confidence,
            "reason": self.reason,
            "section_override_reasons": self.section_override_reasons,
            "catalog_version": self.catalog_version,
            "catalog_hash": self.catalog_hash,
        }


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


def execution_config_payload(
    configs: tuple[SectionConfig, ...],
    routing: ExecutionRouting | None = None,
) -> dict:
    """Serialize execution configs for CLI/Gradio inspection or editing."""

    payload = {
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
    if routing is not None:
        payload["routing"] = routing.to_dict()
    return payload


class RuleBasedDrumExecutionAgent:
    def generate(self, structure: SongStructure, feels: tuple[DrumFeel, ...], seed: int) -> tuple[SectionConfig, ...]:
        return compile_execution_config(structure, feels)


class LLMDrumExecutionAgent:
    """OpenAI-compatible compiler from validated drum feelings to drum config."""

    def __init__(self, client):
        self.client = client

    def generate_from_plan_payload(
        self,
        plan_payload: dict,
        seed: int,
        preset: str | None = None,
        groove: str | None = None,
    ) -> tuple[SectionConfig, ...]:
        """Compile the first Agent payload without pre-parsing its feel fields."""

        _, configs = self.generate_execution_plan(plan_payload, seed, preset, groove)
        return configs

    def generate_execution_plan(
        self,
        plan_payload: dict,
        seed: int,
        preset: str | None = None,
        groove: str | None = None,
    ) -> tuple[ExecutionRouting, tuple[SectionConfig, ...]]:
        """Route style/groove with the live skill, then compile and validate sections."""

        context = {
            "selected_style": preset,
            "selected_global_groove": groove,
            "plan": plan_payload,
        }
        system_prompt = _SYSTEM_PROMPT + "\n\n" + build_routing_skill_context(preset, groove)
        correction = None
        for attempt in range(2):
            request = dict(context)
            if correction:
                request["validation_error_to_fix"] = correction
            payload = self.client.complete_json(system_prompt, json.dumps(request, ensure_ascii=False), seed)
            try:
                configs = parse_section_config(payload)
                routing, configs = validate_execution_routing(payload, configs, preset, groove)
                return routing, configs
            except ValueError as exc:
                correction = str(exc)
                if attempt:
                    raise
        raise ValueError("execution routing failed")

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

The appended route-drum-style-groove skill contains the authoritative live
style/groove catalog and routing policy. Follow its locked/free constraints.
Return a concrete non-free routing.style and routing.global_groove. Start every
section with global_groove. If a section truly needs a different skeleton, put
a concise rhythm-based explanation in routing.section_override_reasons using
the section name as key. Do not use groove changes for energy changes.

cymbal_role may be none, closed_hat_quarters, closed_hat_eighths,
open_hat_quarters, ride_quarters, ride_eighths, or ride_bell_offbeats. Use this
for a sustained Hat/Ride pattern; do not misuse required for a continuous
cymbal role. Curves override linear start/end values and are appropriate for
rise-then-fall sections. dna_overrides may use DrummerDNA fields such as
backbeat_weight, syncopation, swing, mutation, skeleton_strength,
backbeat_variation, ornament_amount, hat_openness, fill_vocabulary,
dynamic_shape, groove_anchor, pulse, low_bias, mid_bias, and high_density.
Do not put groove inside dna_overrides; use the top-level groove field.
Return exactly {\"routing\": {...}, \"sections\": [...]}. routing needs style,
global_groove, style_source (ui_locked or agent_routed), groove_source
(ui_locked or agent_routed), confidence (0-1), reason, and
section_override_reasons. Catalog version/hash are filled by the program."""


def validate_execution_routing(
    payload: dict,
    configs: tuple[SectionConfig, ...],
    ui_style: str | None,
    ui_groove: str | None,
) -> tuple[ExecutionRouting, tuple[SectionConfig, ...]]:
    raw = payload.get("routing") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        raise ValueError("execution output requires a routing object")
    style = str(raw.get("style", "")).strip()
    global_groove = str(raw.get("global_groove", "")).strip()
    if style == "free" or not style_exists(style):
        raise ValueError("routing.style must be a concrete catalog style")
    if global_groove == "free" or groove_owner(global_groove) != style:
        raise ValueError("routing.global_groove must be a concrete groove inside routing.style")
    style_locked = bool(ui_style and ui_style != "free")
    groove_locked = bool(ui_groove and ui_groove != "free")
    if style_locked and style != ui_style:
        raise ValueError(f"routing style must remain locked to {ui_style}")
    if groove_locked and global_groove != ui_groove:
        raise ValueError(f"global groove must remain locked to {ui_groove}")

    normalized = tuple(
        replace(config, groove=config.groove or global_groove)
        for config in configs
    )
    if any(groove_owner(config.groove) != style for config in normalized):
        raise ValueError("every section groove must belong to the routed style")
    if groove_locked and any(config.groove != ui_groove for config in normalized):
        raise ValueError("a locked UI groove must be used by every section")
    reasons = raw.get("section_override_reasons", {})
    if not isinstance(reasons, dict):
        raise ValueError("routing.section_override_reasons must be an object")
    overrides = [config.name for config in normalized if config.groove != global_groove]
    missing_reasons = [name for name in overrides if not str(reasons.get(name, "")).strip()]
    if missing_reasons:
        raise ValueError(f"groove overrides require rhythm-based reasons: {', '.join(missing_reasons)}")
    unique_grooves = {config.groove for config in normalized}
    if len(unique_grooves) > 2 and not bool(raw.get("exceptional_multiple_grooves")):
        raise ValueError("more than two grooves requires exceptional_multiple_grooves=true")
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("routing confidence must be numeric") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("routing confidence must be between 0 and 1")
    metadata = routing_catalog_metadata()
    return ExecutionRouting(
        style=style,
        global_groove=global_groove,
        style_source="ui_locked" if style_locked else "agent_routed",
        groove_source="ui_locked" if groove_locked else "agent_routed",
        confidence=confidence,
        reason=str(raw.get("reason", "")).strip(),
        section_override_reasons={str(key): str(value) for key, value in reasons.items()},
        catalog_version=metadata["catalog_version"],
        catalog_hash=metadata["catalog_hash"],
    ), normalized


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

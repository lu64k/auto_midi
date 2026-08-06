from __future__ import annotations

from dataclasses import dataclass, replace
import random

from .drummer_dna import DrummerDNA
from .section_config import SectionConfig
from .text_parser import BarText, TextMap
from .time_signature import TimeSignature, parse_time_signature
from .rock_patterns import pattern_steps, rock_pattern
from .groove import GROOVE_ANCHORS, GROOVE_PROFILES, GROOVE_PULSES


STEPS_PER_BAR = 16
TICKS_PER_BEAT = 480
TICKS_PER_STEP = TICKS_PER_BEAT // 4


@dataclass(frozen=True)
class DrumEvent:
    bar: int  # Zero-based bar index. 从 0 开始的小节索引。
    step: int  # Sixteenth-note grid step inside the bar, 0-15. 小节内 16 分音符网格步位，范围 0-15。
    voice: str  # Drum voice name, e.g. kick, snare, closed_hat. 鼓组声部名称，如 kick、snare、closed_hat。
    velocity: int  # MIDI velocity, 1-127. MIDI 力度值，范围 1-127。
    duration_steps: int = 1  # Event duration in sixteenth-note steps. 事件时长，单位为 16 分音符步数。
    offset_ticks: int = 0  # Timing offset in MIDI ticks for swing/human feel. 时值偏移量（MIDI tick），用于 swing/人性化。

    bar_length_ticks: int = STEPS_PER_BAR * TICKS_PER_STEP

    @property
    def absolute_tick(self) -> int:
        return self.bar * self.bar_length_ticks + self.step * TICKS_PER_STEP + self.offset_ticks

    @property
    def duration_ticks(self) -> int:
        return max(24, self.duration_steps * TICKS_PER_STEP // 2)


def generate_events(
    text_map: TextMap,
    dna: DrummerDNA,
    rng: random.Random,
    intensity: int,
    fill: int,
    section_configs: tuple[SectionConfig, ...] | None = None,
    time_signature: TimeSignature | str = "4/4",
) -> list[DrumEvent]:
    global STEPS_PER_BAR
    STEPS_PER_BAR = parse_time_signature(time_signature).steps_per_bar
    events: list[DrumEvent] = []
    previous_bar_events: list[DrumEvent] = []

    for bar in text_map.bars:
        section = _section_for_bar(text_map, bar, section_configs)
        section_position = _section_position(text_map, bar)
        section_bar = _section_bar_number(text_map, bar)
        bar_intensity = _curve_or_interpolate(
            section.intensity_curve if section else (),
            section_bar,
            section.intensity_start if section and section.intensity_start is not None else intensity,
            section.intensity_end if section and section.intensity_end is not None else intensity,
            section_position,
        )
        bar_density = _curve_or_interpolate(
            section.density_curve if section else (),
            section_bar,
            section.density_start if section and section.density_start is not None else 0.5,
            section.density_end if section and section.density_end is not None else 0.5,
            section_position,
        )
        bar_dna = _apply_section_dna(dna, section, bar_density)
        bar_fill = section.fill if section and section.fill is not None else fill
        base_velocity = int(45 + bar_intensity * 0.55)
        accents = token_steps(bar)
        rests = punctuation_steps(bar)
        bar_events = []
        bar_events.extend(_memory_events(bar, bar_dna, rng, previous_bar_events))
        bar_events.extend(_low_events(bar, bar_dna, rng, base_velocity, accents, rests))
        bar_events.extend(_mid_events(bar, bar_dna, rng, base_velocity, accents, rests))
        bar_events.extend(_high_events(bar, bar_dna, rng, base_velocity, accents, rests, section))

        if should_fill(bar, bar_dna, rng, bar_fill, section, section_position):
            bar_events.extend(_fill_events(bar, bar_dna, rng, base_velocity))

        if section is None and (bar.index == 0 or bar.section != text_map.bars[bar.index - 1].section):
            bar_events.append(DrumEvent(bar.index, 0, "crash", _vel(base_velocity + 18, rng)))

        bar_events = _filter_allowed_voices(bar_events, section)
        bar_events = _apply_dynamic_shape(bar_events, bar_dna)
        events.extend(bar_events)
        previous_bar_events = bar_events

    events = _ensure_section_voice_rules(events, text_map, section_configs)
    bar_length_ticks = STEPS_PER_BAR * TICKS_PER_STEP
    events = [replace(event, bar_length_ticks=bar_length_ticks) for event in _dedupe(events)]
    return sorted(events, key=lambda event: (event.absolute_tick, event.voice))


def token_steps(bar: BarText) -> set[int]:
    if not bar.token_units:
        return set()
    total = max(1, bar.char_count)
    steps = {
        min(STEPS_PER_BAR - 1, round(token.start_syllable * STEPS_PER_BAR / total))
        for token in bar.token_units
    }
    for phrase in bar.phrases:
        steps.add(min(STEPS_PER_BAR - 1, round(phrase.start_syllable * STEPS_PER_BAR / total)))
    return steps


def punctuation_steps(bar: BarText) -> set[int]:
    count = max(1, bar.char_count)
    steps = {
        min(STEPS_PER_BAR - 1, round(position * STEPS_PER_BAR / count))
        for position in bar.punctuation_positions
    }
    for phrase in bar.phrases:
        if phrase.pause_strength >= 0.5:
            steps.add(min(STEPS_PER_BAR - 1, round(phrase.end_syllable * STEPS_PER_BAR / count)))
    return steps


def phrase_end_steps(bar: BarText) -> set[int]:
    count = max(1, bar.char_count)
    return {
        min(STEPS_PER_BAR - 1, round(phrase.end_syllable * STEPS_PER_BAR / count))
        for phrase in bar.phrases
        if phrase.pause_strength >= 0.5 or phrase.rhyme_key
    }


def should_fill(
    bar: BarText,
    dna: DrummerDNA,
    rng: random.Random,
    fill: int,
    section: SectionConfig | None = None,
    section_position: float = 0.0,
) -> bool:
    if section and section.fill_mode == "none":
        return False
    if section and section.fill_mode == "last_bar" and section_position < 0.999:
        return False
    if section and section.fill_mode == "last_2_bars":
        first_allowed = max(1, section.bars - 1)
        current_bar = 1 if section.bars <= 1 else round(section_position * (section.bars - 1)) + 1
        if current_bar < first_allowed:
            return False
    if section and section.fill_mode == "section_end" and not bar.ends_section:
        return False
    chance = fill / 100.0 * dna.fill_aggression
    if section and section.fill_mode == "every_4":
        if (bar.index + 1) % 4 != 0:
            return False
    elif bar.ends_section:
        chance += 0.35 * dna.fill_aggression
    elif not section and (bar.index + 1) % 4 == 0:
        chance += 0.15 * dna.fill_aggression
    return rng.random() < min(0.9, chance)


def _section_for_bar(
    text_map: TextMap,
    bar: BarText,
    section_configs: tuple[SectionConfig, ...] | None,
) -> SectionConfig | None:
    if not section_configs:
        return None
    if bar.section >= len(section_configs):
        raise ValueError(f"no section config for parsed section {bar.section}")
    section = section_configs[bar.section]
    section_bar_count = sum(1 for item in text_map.bars if item.section == bar.section)
    if section_bar_count != section.bars:
        raise ValueError(
            f"section {bar.section} ({section.name}) expects {section.bars} bars, "
            f"but input text contains {section_bar_count} bars"
        )
    return section


def _section_position(text_map: TextMap, bar: BarText) -> float:
    section_bars = [item for item in text_map.bars if item.section == bar.section]
    if len(section_bars) <= 1:
        return 1.0
    return section_bars.index(bar) / (len(section_bars) - 1)


def _section_bar_number(text_map: TextMap, bar: BarText) -> int:
    section_bars = [item for item in text_map.bars if item.section == bar.section]
    return section_bars.index(bar) + 1


def _apply_section_dna(
    dna: DrummerDNA,
    section: SectionConfig | None,
    density: float,
) -> DrummerDNA:
    if section is None:
        return dna
    overrides = dict(section.dna_overrides)
    for key in overrides:
        if not hasattr(dna, key):
            raise ValueError(f"unknown DrummerDNA override: {key}")
        if key == "style":
            raise ValueError("section-level style override is not supported")
    values = {}
    if section.groove:
        values.update(GROOVE_PROFILES[section.groove])
        values["groove"] = section.groove
        values["groove_anchor"] = GROOVE_ANCHORS[section.groove]
        values["pulse"] = GROOVE_PULSES.get(section.groove, dna.pulse)
    values.update(overrides)
    density_scale = max(0.0, min(2.0, density * 2.0))
    for key in ("low_bias", "mid_bias", "high_density"):
        if key not in overrides:
            values[key] = max(0.0, min(1.0, getattr(dna, key) * density_scale))
    if "skeleton_strength" not in overrides:
        base = float(values.get("skeleton_strength", dna.skeleton_strength))
        values["skeleton_strength"] = max(0.02, min(1.0, base * min(1.0, density_scale)))
    if "ornament_amount" not in overrides:
        base = float(values.get("ornament_amount", dna.ornament_amount))
        values["ornament_amount"] = max(0.0, min(1.0, base * min(1.25, density_scale)))
    return replace(dna, **values)


def _filter_allowed_voices(events: list[DrumEvent], section: SectionConfig | None) -> list[DrumEvent]:
    if section is None or not section.allowed_voices:
        return events
    allowed = set(section.allowed_voices)
    return [event for event in events if event.voice in allowed]


def _ensure_section_voice_rules(
    events: list[DrumEvent],
    text_map: TextMap,
    section_configs: tuple[SectionConfig, ...] | None,
) -> list[DrumEvent]:
    if not section_configs:
        return events
    result = list(events)
    occupied = {(event.bar, event.step, event.voice) for event in result}
    for section_index, section in enumerate(section_configs):
        bars = [bar for bar in text_map.bars if bar.section == section_index]
        if not bars:
            continue
        section_events = [event for event in result if event.bar in {bar.index for bar in bars}]
        voices = tuple(dict.fromkeys((*section.required_voices, *section.voice_placements.keys())))
        for voice in voices:
            placement = section.voice_placements.get(voice, "auto")
            if placement == "auto" and any(event.voice == voice for event in section_events):
                continue
            for bar_index, step in _voice_targets(voice, placement, bars):
                key = (bar_index, step, voice)
                if key in occupied:
                    continue
                local_bar = next(index for index, bar in enumerate(bars, start=1) if bar.index == bar_index)
                position = 1.0 if len(bars) <= 1 else (local_bar - 1) / (len(bars) - 1)
                start = section.intensity_start if section.intensity_start is not None else 50
                end = section.intensity_end if section.intensity_end is not None else start
                intensity = _curve_or_interpolate(section.intensity_curve, local_bar, start, end, position)
                velocity = max(1, min(127, int(53 + intensity * 0.55)))
                result.append(DrumEvent(bar_index, step, voice, velocity))
                occupied.add(key)
    return result


def _voice_targets(voice: str, placement: str, bars: list[BarText]) -> list[tuple[int, int]]:
    if placement == "auto":
        if voice in {"snare", "rim", "clap"}:
            return [(bars[0].index, min(_backbeat_steps()))]
        return [(bars[0].index, 0)]
    if placement in {"section_start", "first_bar"}:
        return [(bars[0].index, 0)]
    if placement == "section_end":
        return [(bars[-1].index, STEPS_PER_BAR - 1)]
    if placement == "last_bar":
        return [(bars[-1].index, 0)]
    if placement == "every_bar":
        return [(bar.index, 0) for bar in bars]
    targets = []
    for bar in bars:
        for phrase in bar.phrases:
            syllable = phrase.start_syllable if placement == "phrase_start" else phrase.end_syllable
            step = min(STEPS_PER_BAR - 1, round(syllable * STEPS_PER_BAR / max(1, bar.char_count)))
            targets.append((bar.index, step))
    return targets or [(bars[0].index, 0)]


def _interpolate(start: float, end: float, position: float) -> float:
    return start + (end - start) * max(0.0, min(1.0, position))


def _curve_or_interpolate(
    curve: tuple[tuple[int, float], ...], bar_number: int,
    start: float, end: float, position: float,
) -> float:
    if not curve:
        return _interpolate(start, end, position)
    if bar_number <= curve[0][0]:
        return curve[0][1]
    if bar_number >= curve[-1][0]:
        return curve[-1][1]
    for (left_bar, left_value), (right_bar, right_value) in zip(curve, curve[1:]):
        if left_bar <= bar_number <= right_bar:
            local = (bar_number - left_bar) / max(1, right_bar - left_bar)
            return _interpolate(left_value, right_value, local)
    return curve[-1][1]


def _low_events(
    bar: BarText,
    dna: DrummerDNA,
    rng: random.Random,
    base_velocity: int,
    accents: set[int],
    rests: set[int],
) -> list[DrumEvent]:
    events = []
    for step, boost in _anchor_kick_steps(dna, rng):
        events.append(DrumEvent(bar.index, step, "kick", _vel(base_velocity + boost, rng)))
    if dna.kick_snare_lock > 0.55 and rng.random() < dna.kick_snare_lock * 0.5 * dna.ornament_amount:
        events.append(DrumEvent(bar.index, rng.choice([8, 10]), "kick", _vel(base_velocity + 2, rng)))
    candidates = [step for step in accents if step not in rests and step % 4 != 0]
    for step in candidates:
        chance = dna.low_bias * dna.accent_follow * (1.2 - dna.kick_snare_lock * 0.45)
        if step in {3, 6, 10, 14}:
            chance += dna.syncopation * 0.25
        if rng.random() < chance * 0.55 * dna.ornament_amount:
            events.append(DrumEvent(bar.index, step, "kick", _vel(base_velocity + 4, rng), offset_ticks=_swing_offset(step, dna)))
    if rng.random() > dna.repetition and rng.random() < dna.ornament_amount:
        step = rng.choice([7, 11, 15])
        events.append(DrumEvent(bar.index, step, "kick", _vel(base_velocity - 4, rng), offset_ticks=_swing_offset(step, dna)))
    return events


def _mid_events(
    bar: BarText,
    dna: DrummerDNA,
    rng: random.Random,
    base_velocity: int,
    accents: set[int],
    rests: set[int],
) -> list[DrumEvent]:
    events = []
    for step, boost in _anchor_mid_steps(dna):
        pattern = rock_pattern(dna.groove)
        anchor_chance = (
            0.15 + dna.skeleton_strength * 0.85
            if pattern
            else max(
                0.75,
                0.98 - dna.backbeat_variation * 0.10 - (1.0 - dna.skeleton_strength) * 0.06,
            )
        )
        if rng.random() < anchor_chance:
            events.append(DrumEvent(bar.index, step, "snare", _vel(base_velocity + boost + int(dna.backbeat_weight * 8), rng)))
    for step in accents:
        if dna.groove_anchor == "one_drop" and step == 0:
            continue
        if step in rests or step in _backbeat_steps():
            continue
        if rng.random() < dna.mid_bias * dna.accent_follow * 0.28 * dna.ornament_amount:
            voice = "clap" if rng.random() < 0.35 else "rim"
            events.append(DrumEvent(bar.index, step, voice, _vel(base_velocity - 10, rng), offset_ticks=_swing_offset(step, dna)))
        elif rng.random() < dna.ghost_note_bias * 0.22 * dna.ornament_amount:
            voice = "rim" if rng.random() < 0.65 else "snare"
            events.append(DrumEvent(bar.index, step, voice, _vel(base_velocity - 28, rng), offset_ticks=_swing_offset(step, dna)))
    for step in _eighth_steps(1, 3, 5, 7):
        if step not in rests and rng.random() < dna.ghost_note_bias * dna.syncopation * 0.2 * dna.ornament_amount:
            events.append(DrumEvent(bar.index, step, "rim", _vel(base_velocity - 32, rng), offset_ticks=_swing_offset(step, dna)))
    for step in phrase_end_steps(bar):
        if step not in rests and step not in _backbeat_steps() and rng.random() < dna.mid_bias * 0.22 * dna.ornament_amount:
            events.append(DrumEvent(bar.index, step, "rim", _vel(base_velocity - 12, rng), offset_ticks=_swing_offset(step, dna)))
    if bar.has_strong_ending and rng.random() < dna.mid_bias * dna.ornament_amount:
        events.append(DrumEvent(bar.index, 15, "clap", _vel(base_velocity + 6, rng), offset_ticks=_swing_offset(15, dna)))
    return events


def _high_events(
    bar: BarText,
    dna: DrummerDNA,
    rng: random.Random,
    base_velocity: int,
    accents: set[int],
    rests: set[int],
    section: SectionConfig | None,
) -> list[DrumEvent]:
    events: list[DrumEvent] = []
    if section and section.cymbal_role:
        return _cymbal_role_events(bar, section.cymbal_role, rng, base_velocity)
    interval = 4 if dna.pulse == 4 else 2 if dna.pulse == 8 else 1
    pattern = rock_pattern(dna.groove)
    hat_steps = pattern_steps(pattern, "hat_steps", STEPS_PER_BAR) if pattern else tuple(range(0, STEPS_PER_BAR, interval))
    for step in hat_steps:
        if step >= STEPS_PER_BAR:
            continue
        if pattern and rng.random() < dna.backbeat_variation * 0.15:
            continue
        if not pattern and step in rests and rng.random() < dna.rest_follow:
            continue
        hat_chance = 0.15 + dna.skeleton_strength * 0.85 if pattern else max(dna.high_density, 0.25 + dna.skeleton_strength * 0.65)
        if rng.random() < hat_chance:
            velocity = base_velocity - 18 + (9 if step in accents else 0)
            voice = _hat_voice(step, dna, rng)
            events.append(DrumEvent(bar.index, step, voice, _vel(velocity, rng), offset_ticks=_swing_offset(step, dna)))

    for step in accents:
        if step not in rests and rng.random() < dna.mutation * 0.35 * dna.ornament_amount:
            events.append(DrumEvent(bar.index, step, _hat_voice(step, dna, rng), _vel(base_velocity - 8, rng), offset_ticks=_swing_offset(step, dna)))

    if rng.random() < dna.syncopation * (0.2 + dna.hat_openness * 0.45) * dna.ornament_amount:
        events.append(DrumEvent(bar.index, rng.choice(_eighth_steps(3, 5, 7)), "open_hat", _vel(base_velocity - 6, rng)))
    return events


def _cymbal_role_events(bar: BarText, role: str, rng: random.Random, base_velocity: int) -> list[DrumEvent]:
    if role == "none":
        return []
    voice = "ride" if role.startswith("ride") else "open_hat" if role.startswith("open_hat") else "closed_hat"
    if role.endswith("quarters"):
        steps = range(0, STEPS_PER_BAR, max(1, STEPS_PER_BAR // 4))
    elif role == "ride_bell_offbeats":
        step_size = max(1, STEPS_PER_BAR // 4)
        steps = range(step_size // 2, STEPS_PER_BAR, step_size)
    else:
        steps = range(0, STEPS_PER_BAR, max(1, STEPS_PER_BAR // 8))
    return [DrumEvent(bar.index, step, voice, _vel(base_velocity - 14, rng)) for step in steps]


def _fill_events(bar: BarText, dna: DrummerDNA, rng: random.Random, base_velocity: int) -> list[DrumEvent]:
    if dna.fill_vocabulary == "silence":
        return []
    start = rng.choice(_eighth_steps(4, 5, 6))
    voices = _fill_voices(dna.fill_vocabulary)
    events: list[DrumEvent] = []
    for step in range(start, STEPS_PER_BAR):
        if rng.random() < 0.35 + dna.fill_aggression * 0.45:
            voice = rng.choice(voices)
            velocity = base_velocity + int((step - start) * 1.8)
            events.append(DrumEvent(bar.index, step, voice, _vel(velocity, rng), offset_ticks=_swing_offset(step, dna)))
    return events


def _memory_events(
    bar: BarText,
    dna: DrummerDNA,
    rng: random.Random,
    previous_bar_events: list[DrumEvent],
) -> list[DrumEvent]:
    if not previous_bar_events or rng.random() > dna.phrase_memory:
        return []
    remembered = []
    keep_chance = 0.15 + dna.phrase_memory * 0.45
    for event in previous_bar_events:
        if dna.groove_anchor == "one_drop" and event.step == 0 and event.voice in {"kick", "snare", "rim", "clap"}:
            continue
        if event.voice == "crash" or event.step in _backbeat_steps():
            continue
        if rng.random() < keep_chance and event.voice in {"kick", "closed_hat", "open_hat", "rim"}:
            velocity = max(1, min(127, int(event.velocity * rng.uniform(0.85, 1.05))))
            remembered.append(
                DrumEvent(
                    bar=bar.index,
                    step=event.step,
                    voice=event.voice,
                    velocity=velocity,
                    duration_steps=event.duration_steps,
                    offset_ticks=event.offset_ticks,
                )
            )
    return remembered


def _hat_voice(step: int, dna: DrummerDNA, rng: random.Random) -> str:
    if dna.style == "jazz":
        return "ride"
    if step in set(_eighth_steps(3, 5, 7)) and rng.random() < dna.hat_openness:
        return "open_hat"
    if rng.random() < dna.hat_openness * 0.2:
        return "open_hat"
    return "closed_hat"


def _fill_voices(fill_vocabulary: str) -> list[str]:
    if fill_vocabulary == "snare_roll":
        return ["snare", "rim"]
    if fill_vocabulary == "tom_run":
        return ["mid_tom", "low_tom", "snare"]
    if fill_vocabulary == "hat_roll":
        return ["closed_hat", "open_hat", "snare"]
    return ["snare", "mid_tom", "low_tom", "closed_hat"]


def _anchor_kick_steps(dna: DrummerDNA, rng: random.Random) -> list[tuple[int, int]]:
    pattern = rock_pattern(dna.groove)
    if pattern:
        kick_steps = pattern_steps(pattern, "kick_steps", STEPS_PER_BAR)
        result = [(kick_steps[0], 12)]
        keep_chance = 0.10 + dna.skeleton_strength * 0.90
        result.extend((step, 4) for step in kick_steps[1:] if rng.random() < keep_chance)
        return result
    if dna.groove_anchor == "one_drop":
        return [(8, 10)]
    if dna.groove_anchor == "four_on_floor":
        return [(0, 8), (4, 1), (8, 5), (12, 1)]
    if dna.groove_anchor == "offbeat_push":
        steps = [(0, 6)]
        if rng.random() < 0.75:
            steps.append((6, 0))
        return steps
    if dna.groove_anchor == "floating":
        return [(rng.choice([3, 6, 8, 10]), 4)]
    return [(0, 12)] if STEPS_PER_BAR == 16 else [(0, 10), (STEPS_PER_BAR // 2, 4)]


def _anchor_mid_steps(dna: DrummerDNA) -> list[tuple[int, int]]:
    pattern = rock_pattern(dna.groove)
    if pattern:
        return [(step, 10) for step in pattern_steps(pattern, "snare_steps", STEPS_PER_BAR)]
    if dna.groove_anchor == "one_drop":
        return [(8, 12)]
    if dna.groove_anchor == "floating":
        return [(4, 6), (12, 5)]
    if dna.groove_anchor == "offbeat_push":
        return [(4, 8), (10, 5), (12, 8)]
    if STEPS_PER_BAR == 12:
        return [(6, 10)]
    return [(4, 10), (12, 8)]


def _eighth_steps(*positions: int) -> list[int]:
    return [min(STEPS_PER_BAR - 1, round(position * STEPS_PER_BAR / 8)) for position in positions]


def _backbeat_steps() -> set[int]:
    return {6} if STEPS_PER_BAR == 12 else {4, 12}


def _apply_dynamic_shape(events: list[DrumEvent], dna: DrummerDNA) -> list[DrumEvent]:
    shaped = []
    for event in events:
        factor = _dynamic_factor(event.step, dna.dynamic_shape)
        shaped.append(
            DrumEvent(
                bar=event.bar,
                step=event.step,
                voice=event.voice,
                velocity=max(1, min(127, int(event.velocity * factor))),
                duration_steps=event.duration_steps,
                offset_ticks=event.offset_ticks,
            )
        )
    return shaped


def _dynamic_factor(step: int, shape: str) -> float:
    position = step / max(1, STEPS_PER_BAR - 1)
    if shape == "front_heavy":
        return 1.12 - position * 0.18
    if shape == "back_heavy":
        return 0.9 + position * 0.22
    if shape == "crescendo":
        return 0.82 + position * 0.35
    if shape == "decrescendo":
        return 1.15 - position * 0.32
    if shape == "pocket":
        return 1.08 if step in {0, 4, 8, 12} else 0.92
    return 1.0


def _dedupe(events: list[DrumEvent]) -> list[DrumEvent]:
    seen: set[tuple[int, int, str]] = set()
    result: list[DrumEvent] = []
    for event in events:
        key = (event.bar, event.step, event.voice)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def _vel(value: int, rng: random.Random) -> int:
    return max(1, min(127, int(value + rng.randint(-7, 7))))


def _swing_offset(step: int, dna: DrummerDNA) -> int:
    pattern = rock_pattern(dna.groove)
    if pattern and pattern.swing_ratio and step % 4 == 2:
        return int(TICKS_PER_STEP * pattern.swing_ratio)
    if dna.style in {"blues", "jazz"} and step % 4 == 2:
        return int(TICKS_PER_STEP * dna.swing)
    if step % 2 == 1:
        return int(TICKS_PER_STEP * dna.swing)
    return 0

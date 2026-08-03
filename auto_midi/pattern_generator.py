from __future__ import annotations

from dataclasses import dataclass, replace
import random

from .drummer_dna import DrummerDNA
from .section_config import SectionConfig
from .text_parser import BarText, TextMap


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

    @property
    def absolute_tick(self) -> int:
        return self.bar * STEPS_PER_BAR * TICKS_PER_STEP + self.step * TICKS_PER_STEP + self.offset_ticks

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
) -> list[DrumEvent]:
    events: list[DrumEvent] = []
    previous_bar_events: list[DrumEvent] = []

    for bar in text_map.bars:
        section = _section_for_bar(text_map, bar, section_configs)
        section_position = _section_position(text_map, bar)
        bar_intensity = _interpolate(
            section.intensity_start if section and section.intensity_start is not None else intensity,
            section.intensity_end if section and section.intensity_end is not None else intensity,
            section_position,
        )
        bar_density = _interpolate(
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
        bar_events.extend(_high_events(bar, bar_dna, rng, base_velocity, accents, rests))

        if should_fill(bar, bar_dna, rng, bar_fill, section, section_position):
            bar_events.extend(_fill_events(bar, bar_dna, rng, base_velocity))

        if bar.index == 0 or bar.section != text_map.bars[bar.index - 1].section:
            bar_events.append(DrumEvent(bar.index, 0, "crash", _vel(base_velocity + 18, rng)))

        bar_events = _apply_dynamic_shape(bar_events, bar_dna)
        events.extend(bar_events)
        previous_bar_events = bar_events

    return sorted(_dedupe(events), key=lambda event: (event.absolute_tick, event.voice))


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
    if section and section.fill_mode == "last_2_bars" and section_position < 0.5:
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


def _apply_section_dna(
    dna: DrummerDNA,
    section: SectionConfig | None,
    density: float,
) -> DrummerDNA:
    if section is None:
        return dna
    values = dict(section.dna_overrides)
    for key in values:
        if not hasattr(dna, key):
            raise ValueError(f"unknown DrummerDNA override: {key}")
        if key == "style":
            raise ValueError("section-level style override is not supported")
    density_scale = max(0.0, min(2.0, density * 2.0))
    for key in ("low_bias", "mid_bias", "high_density"):
        if key not in values:
            values[key] = max(0.0, min(1.0, getattr(dna, key) * density_scale))
    return replace(dna, **values)


def _interpolate(start: float, end: float, position: float) -> float:
    return start + (end - start) * max(0.0, min(1.0, position))


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
    if dna.kick_snare_lock > 0.55 and rng.random() < dna.kick_snare_lock * 0.5:
        events.append(DrumEvent(bar.index, rng.choice([8, 10]), "kick", _vel(base_velocity + 2, rng)))
    candidates = [step for step in accents if step not in rests and step % 4 != 0]
    for step in candidates:
        chance = dna.low_bias * dna.accent_follow * (1.2 - dna.kick_snare_lock * 0.45)
        if step in {3, 6, 10, 14}:
            chance += dna.syncopation * 0.25
        if rng.random() < chance * 0.55:
            events.append(DrumEvent(bar.index, step, "kick", _vel(base_velocity + 4, rng), offset_ticks=_swing_offset(step, dna)))
    if rng.random() > dna.repetition:
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
        if rng.random() < 0.2 + dna.backbeat_weight * 0.8:
            events.append(DrumEvent(bar.index, step, "snare", _vel(base_velocity + boost + int(dna.backbeat_weight * 8), rng)))
    for step in accents:
        if dna.groove_anchor == "one_drop" and step == 0:
            continue
        if step in rests or step in {4, 12}:
            continue
        if rng.random() < dna.mid_bias * dna.accent_follow * 0.28:
            voice = "clap" if rng.random() < 0.35 else "rim"
            events.append(DrumEvent(bar.index, step, voice, _vel(base_velocity - 10, rng), offset_ticks=_swing_offset(step, dna)))
        elif rng.random() < dna.ghost_note_bias * 0.22:
            voice = "rim" if rng.random() < 0.65 else "snare"
            events.append(DrumEvent(bar.index, step, voice, _vel(base_velocity - 28, rng), offset_ticks=_swing_offset(step, dna)))
    for step in (2, 6, 10, 14):
        if step not in rests and rng.random() < dna.ghost_note_bias * dna.syncopation * 0.2:
            events.append(DrumEvent(bar.index, step, "rim", _vel(base_velocity - 32, rng), offset_ticks=_swing_offset(step, dna)))
    for step in phrase_end_steps(bar):
        if step not in rests and step not in {4, 12} and rng.random() < dna.mid_bias * 0.22:
            events.append(DrumEvent(bar.index, step, "rim", _vel(base_velocity - 12, rng), offset_ticks=_swing_offset(step, dna)))
    if bar.has_strong_ending and rng.random() < dna.mid_bias:
        events.append(DrumEvent(bar.index, 15, "clap", _vel(base_velocity + 6, rng), offset_ticks=_swing_offset(15, dna)))
    return events


def _high_events(
    bar: BarText,
    dna: DrummerDNA,
    rng: random.Random,
    base_velocity: int,
    accents: set[int],
    rests: set[int],
) -> list[DrumEvent]:
    events: list[DrumEvent] = []
    interval = 4 if dna.pulse == 4 else 2 if dna.pulse == 8 else 1
    for step in range(0, STEPS_PER_BAR, interval):
        if step in rests and rng.random() < dna.rest_follow:
            continue
        if rng.random() < dna.high_density:
            velocity = base_velocity - 18 + (9 if step in accents else 0)
            voice = _hat_voice(step, dna, rng)
            events.append(DrumEvent(bar.index, step, voice, _vel(velocity, rng), offset_ticks=_swing_offset(step, dna)))

    for step in accents:
        if step not in rests and rng.random() < dna.mutation * 0.35:
            events.append(DrumEvent(bar.index, step, _hat_voice(step, dna, rng), _vel(base_velocity - 8, rng), offset_ticks=_swing_offset(step, dna)))

    if rng.random() < dna.syncopation * (0.2 + dna.hat_openness * 0.45):
        events.append(DrumEvent(bar.index, rng.choice([6, 10, 14]), "open_hat", _vel(base_velocity - 6, rng)))
    return events


def _fill_events(bar: BarText, dna: DrummerDNA, rng: random.Random, base_velocity: int) -> list[DrumEvent]:
    if dna.fill_vocabulary == "silence":
        return []
    start = rng.choice([8, 10, 12])
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
        if event.voice == "crash" or event.step in {4, 12}:
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
    if step in {6, 10, 14} and rng.random() < dna.hat_openness:
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
    return [(0, 12)]


def _anchor_mid_steps(dna: DrummerDNA) -> list[tuple[int, int]]:
    if dna.groove_anchor == "one_drop":
        return [(8, 12)]
    if dna.groove_anchor == "floating":
        return [(4, 6), (12, 5)]
    if dna.groove_anchor == "offbeat_push":
        return [(4, 8), (10, 5), (12, 8)]
    return [(4, 10), (12, 8)]


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
    if step % 2 == 1:
        return int(TICKS_PER_STEP * dna.swing)
    return 0

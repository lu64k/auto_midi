from __future__ import annotations

from dataclasses import dataclass
import random

from .drummer_dna import DrummerDNA
from .text_parser import BarText, TextMap


STEPS_PER_BAR = 16
TICKS_PER_BEAT = 480
TICKS_PER_STEP = TICKS_PER_BEAT // 4


@dataclass(frozen=True)
class DrumEvent:
    bar: int
    step: int
    voice: str
    velocity: int
    duration_steps: int = 1
    offset_ticks: int = 0

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
) -> list[DrumEvent]:
    events: list[DrumEvent] = []
    base_velocity = int(45 + intensity * 0.55)

    for bar in text_map.bars:
        accents = token_steps(bar)
        rests = punctuation_steps(bar)
        events.extend(_low_events(bar, dna, rng, base_velocity, accents, rests))
        events.extend(_mid_events(bar, dna, rng, base_velocity, accents, rests))
        events.extend(_high_events(bar, dna, rng, base_velocity, accents, rests))

        if should_fill(bar, dna, rng, fill):
            events.extend(_fill_events(bar, dna, rng, base_velocity))

        if bar.index == 0 or bar.section != text_map.bars[bar.index - 1].section:
            events.append(DrumEvent(bar.index, 0, "crash", _vel(base_velocity + 18, rng)))

    return sorted(_dedupe(events), key=lambda event: (event.absolute_tick, event.voice))


def token_steps(bar: BarText) -> set[int]:
    count = max(1, bar.token_count)
    steps = set()
    for index in range(count):
        steps.add(min(STEPS_PER_BAR - 1, round(index * STEPS_PER_BAR / count)))
    return steps


def punctuation_steps(bar: BarText) -> set[int]:
    count = max(1, bar.char_count)
    return {
        min(STEPS_PER_BAR - 1, round(position * STEPS_PER_BAR / count))
        for position in bar.punctuation_positions
    }


def should_fill(bar: BarText, dna: DrummerDNA, rng: random.Random, fill: int) -> bool:
    chance = fill / 100.0 * dna.fill_aggression
    if bar.ends_section:
        chance += 0.35 * dna.fill_aggression
    elif (bar.index + 1) % 4 == 0:
        chance += 0.15 * dna.fill_aggression
    return rng.random() < min(0.9, chance)


def _low_events(
    bar: BarText,
    dna: DrummerDNA,
    rng: random.Random,
    base_velocity: int,
    accents: set[int],
    rests: set[int],
) -> list[DrumEvent]:
    events = [DrumEvent(bar.index, 0, "kick", _vel(base_velocity + 12, rng))]
    candidates = [step for step in accents if step not in rests and step % 4 != 0]
    for step in candidates:
        chance = dna.low_bias * dna.accent_follow
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
    events = [
        DrumEvent(bar.index, 4, "snare", _vel(base_velocity + 10, rng)),
        DrumEvent(bar.index, 12, "snare", _vel(base_velocity + 8, rng)),
    ]
    for step in accents:
        if step in rests or step in {4, 12}:
            continue
        if rng.random() < dna.mid_bias * dna.accent_follow * 0.28:
            voice = "clap" if rng.random() < 0.35 else "rim"
            events.append(DrumEvent(bar.index, step, voice, _vel(base_velocity - 10, rng), offset_ticks=_swing_offset(step, dna)))
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
            events.append(DrumEvent(bar.index, step, "closed_hat", _vel(velocity, rng), offset_ticks=_swing_offset(step, dna)))

    for step in accents:
        if step not in rests and rng.random() < dna.mutation * 0.35:
            events.append(DrumEvent(bar.index, step, "closed_hat", _vel(base_velocity - 8, rng), offset_ticks=_swing_offset(step, dna)))

    if rng.random() < dna.syncopation * 0.35:
        events.append(DrumEvent(bar.index, rng.choice([6, 10, 14]), "open_hat", _vel(base_velocity - 6, rng)))
    return events


def _fill_events(bar: BarText, dna: DrummerDNA, rng: random.Random, base_velocity: int) -> list[DrumEvent]:
    start = rng.choice([8, 10, 12])
    voices = ["snare", "mid_tom", "low_tom"]
    events: list[DrumEvent] = []
    for step in range(start, STEPS_PER_BAR):
        if rng.random() < 0.35 + dna.fill_aggression * 0.45:
            voice = rng.choice(voices)
            velocity = base_velocity + int((step - start) * 1.8)
            events.append(DrumEvent(bar.index, step, voice, _vel(velocity, rng), offset_ticks=_swing_offset(step, dna)))
    return events


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

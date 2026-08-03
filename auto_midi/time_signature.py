"""Time-signature parsing and sixteenth-note grid helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeSignature:
    numerator: int
    denominator: int

    @property
    def steps_per_bar(self) -> int:
        # The generator uses sixteenth notes as its smallest grid unit.
        return self.numerator * 16 // self.denominator

    @property
    def midi_denominator_power(self) -> int:
        power = 0
        denominator = self.denominator
        while denominator > 1 and denominator % 2 == 0:
            denominator //= 2
            power += 1
        if denominator != 1:
            raise ValueError("MIDI time-signature denominator must be a power of two")
        return power

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"


SUPPORTED_TIME_SIGNATURES = {
    "3/4": TimeSignature(3, 4),
    "4/4": TimeSignature(4, 4),
    "6/8": TimeSignature(6, 8),
}


def parse_time_signature(value: str | TimeSignature) -> TimeSignature:
    if isinstance(value, TimeSignature):
        return value
    try:
        return SUPPORTED_TIME_SIGNATURES[value.strip()]
    except (AttributeError, KeyError) as exc:
        choices = ", ".join(SUPPORTED_TIME_SIGNATURES)
        raise ValueError(f"unsupported time signature {value!r}; choose one of {choices}") from exc

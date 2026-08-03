from __future__ import annotations

from pathlib import Path

from .drum_rack import note_for
from .pattern_generator import DrumEvent, TICKS_PER_BEAT
from .time_signature import TimeSignature, parse_time_signature


DRUM_CHANNEL = 9


def write_midi(events: list[DrumEvent], output_path: Path, bpm: int, time_signature: TimeSignature | str = "4/4") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    track = bytearray()
    tempo = int(60_000_000 / bpm)
    track.extend(_varlen(0))
    track.extend(b"\xff\x51\x03")
    track.extend(tempo.to_bytes(3, "big"))
    track.extend(_varlen(0))
    signature = parse_time_signature(time_signature)
    track.extend(bytes([0xFF, 0x58, 0x04, signature.numerator, signature.midi_denominator_power, 0x18, 0x08]))

    midi_messages: list[tuple[int, bytes]] = []
    for event in events:
        note = note_for(event.voice)
        midi_messages.append((event.absolute_tick, bytes([0x90 | DRUM_CHANNEL, note, event.velocity])))
        midi_messages.append((event.absolute_tick + event.duration_ticks, bytes([0x80 | DRUM_CHANNEL, note, 0])))

    current_tick = 0
    for tick, message in sorted(midi_messages, key=lambda item: (item[0], item[1][0])):
        delta = max(0, tick - current_tick)
        track.extend(_varlen(delta))
        track.extend(message)
        current_tick = tick

    track.extend(_varlen(0))
    track.extend(b"\xff\x2f\x00")

    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big")
    header += TICKS_PER_BEAT.to_bytes(2, "big")
    chunk = b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)
    output_path.write_bytes(header + chunk)


def _varlen(value: int) -> bytes:
    buffer = value & 0x7F
    value >>= 7
    while value:
        buffer <<= 8
        buffer |= (value & 0x7F) | 0x80
        value >>= 7

    result = bytearray()
    while True:
        result.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break
    return bytes(result)

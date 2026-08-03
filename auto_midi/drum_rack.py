from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DrumVoice:
    name: str
    midi_note: int
    slot: str


GENERAL_MIDI_DRUMS = {
    "kick": DrumVoice("kick", 36, "low"),
    "rim": DrumVoice("rim", 37, "mid"),
    "snare": DrumVoice("snare", 38, "mid"),
    "clap": DrumVoice("clap", 39, "mid"),
    "low_tom": DrumVoice("low_tom", 45, "low"),
    "mid_tom": DrumVoice("mid_tom", 47, "mid"),
    "closed_hat": DrumVoice("closed_hat", 42, "high"),
    "open_hat": DrumVoice("open_hat", 46, "high"),
    "crash": DrumVoice("crash", 49, "high"),
    "ride": DrumVoice("ride", 51, "high"),
}


def note_for(voice: str) -> int:
    return GENERAL_MIDI_DRUMS[voice].midi_note

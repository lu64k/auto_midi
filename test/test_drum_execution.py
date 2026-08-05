from __future__ import annotations

import unittest
from dataclasses import replace

from auto_midi.drum_execution import compile_execution_config
from auto_midi.drum_feel import RuleBasedDrumFeelAgent
from auto_midi.drummer_dna import generate_dna
from auto_midi.pattern_generator import generate_events
from auto_midi.section_config import SectionConfig
from auto_midi.song_structure import parse_song_structure
from auto_midi.text_parser import parse_text
import random


class DrumExecutionTests(unittest.TestCase):
    def test_compiles_feel_to_section_config(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [
                    {"id": "verse_1", "type": "verse", "bars": 4, "chords": []},
                    {"id": "chorus_1", "type": "chorus", "bars": 8, "chords": [["E"]] * 8},
                ],
            }
        )
        feels = RuleBasedDrumFeelAgent().generate(structure, "rock", "classic_rock", seed=7)
        configs = compile_execution_config(structure, feels)
        self.assertEqual([config.name for config in configs], ["verse_1", "chorus_1"])
        self.assertEqual(configs[1].chord_bars, (("E",),) * 8)
        self.assertIn(configs[1].fill_mode, {"section_end", "every_4"})

    def test_rejects_mismatched_feel_ids(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [{"id": "verse_1", "type": "verse", "bars": 2, "chords": []}],
            }
        )
        feel = RuleBasedDrumFeelAgent().generate(structure, "rock", "classic_rock", seed=7)[0]
        with self.assertRaisesRegex(ValueError, "order/ids"):
            compile_execution_config(structure, (replace(feel, section_id="wrong"),))

    def test_allowed_and_required_are_distinct_execution_controls(self) -> None:
        text_map = parse_text("one")
        dna = generate_dna(text_map, random.Random(2), 40, 60, 0, 20, preset="rock", groove="classic_rock")
        config = SectionConfig(
            name="intro",
            bars=1,
            allowed_voices=("snare",),
            required_voices=("snare",),
            fill_mode="none",
        )
        events = generate_events(text_map, dna, random.Random(2), 60, 0, (config,), "4/4")
        self.assertTrue(events)
        self.assertEqual({event.voice for event in events}, {"snare"})


if __name__ == "__main__":
    unittest.main()

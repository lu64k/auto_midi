from __future__ import annotations

import unittest

from auto_midi.drum_feel import RuleBasedDrumFeelAgent
from auto_midi.song_structure import parse_song_structure


class DrumFeelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.structure = parse_song_structure(
            {
                "title": "feel-demo",
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [
                    {"id": "intro", "type": "intro", "bars": 2, "chords": []},
                    {"id": "verse_1", "type": "verse", "bars": 2, "chords": [["E"], ["B"]]},
                    {"id": "chorus_1", "type": "chorus", "bars": 2, "chords": []},
                ],
            }
        )

    def test_generates_one_feel_per_section(self) -> None:
        feels = RuleBasedDrumFeelAgent().generate(self.structure, "rock", "classic_rock", seed=7)
        self.assertEqual([feel.section_id for feel in feels], ["intro", "verse_1", "chorus_1"])
        self.assertEqual(feels[1].chord_context, (("E",), ("B",)))
        self.assertEqual(feels[2].chord_context, ())

    def test_fixed_seed_is_repeatable(self) -> None:
        agent = RuleBasedDrumFeelAgent()
        first = agent.generate(self.structure, "rock", "classic_rock", seed=11)
        second = agent.generate(self.structure, "rock", "classic_rock", seed=11)
        self.assertEqual(first, second)

    def test_chorus_is_more_energetic_than_intro(self) -> None:
        feels = RuleBasedDrumFeelAgent().generate(self.structure, "rock", "classic_rock", seed=3)
        self.assertGreater(feels[2].energy, feels[0].energy)


if __name__ == "__main__":
    unittest.main()

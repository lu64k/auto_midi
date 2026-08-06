from __future__ import annotations

import unittest

from auto_midi.song_structure import (
    parse_song_structure,
    resolved_chord_bars,
    apply_song_structure,
    section_configs_from_song_structure,
    validate_against_lyrics,
)
from auto_midi.text_parser import parse_text


class SongStructureTests(unittest.TestCase):
    def test_section_level_chords_and_empty_section(self) -> None:
        structure = parse_song_structure(
            {
                "title": "demo",
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [
                    {"id": "intro", "type": "intro", "bars": 2, "chords": []},
                    {
                        "id": "verse_1",
                        "type": "verse",
                        "bars": 2,
                        "chords": [["E"], ["B", "C#m"]],
                    },
                ],
            }
        )
        self.assertFalse(structure.sections[0].has_chords)
        self.assertEqual(resolved_chord_bars(structure, "verse_1"), (("E",), ("B", "C#m")))
        validate_against_lyrics(structure, 4)

    def test_flat_chord_list_is_convenience_form(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 100,
                "time_signature": "4/4",
                "sections": [{"id": "chorus_1", "type": "chorus", "bars": 2, "chords": ["A", "E"]}],
            }
        )
        self.assertEqual(structure.sections[0].chord_bars, (("A",), ("E",)))

    def test_repeat_can_explicitly_reuse_chords(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 100,
                "time_signature": "4/4",
                "sections": [
                    {"id": "verse_1", "type": "verse", "bars": 2, "chords": [["E"], ["B"]]},
                    {"id": "verse_2", "type": "verse", "bars": 2, "chords": [], "repeat_of": "verse_1"},
                ],
            }
        )
        self.assertEqual(resolved_chord_bars(structure, "verse_2"), (("E",), ("B",)))

    def test_chord_count_must_match_section_bars(self) -> None:
        with self.assertRaisesRegex(ValueError, "expected 4"):
            parse_song_structure(
                {
                    "bpm": 100,
                    "time_signature": "4/4",
                    "sections": [{"id": "verse_1", "type": "verse", "bars": 4, "chords": ["E", "B"]}],
                }
            )

    def test_structure_converts_to_existing_section_config(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 100,
                "time_signature": "4/4",
                "sections": [
                    {"id": "intro", "type": "intro", "bars": 2, "chords": []},
                    {"id": "chorus_1", "type": "chorus", "bars": 2, "chords": [["A"], ["E"]]},
                ],
            }
        )
        configs = section_configs_from_song_structure(structure, parse_text("one\ntwo\n\nthree\nfour"))
        self.assertEqual([config.name for config in configs], ["intro", "chorus_1"])
        self.assertEqual(configs[1].section_type, "chorus")
        self.assertEqual(configs[1].chord_bars, (("A",), ("E",)))

    def test_structure_controls_boundaries_without_blank_lines(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 100,
                "time_signature": "4/4",
                "sections": [
                    {"id": "intro", "type": "intro", "bars": 1, "chords": []},
                    {"id": "verse_1", "type": "verse", "bars": 3, "chords": []},
                ],
            }
        )
        mapped = apply_song_structure(parse_text("one\ntwo\nthree\nfour"), structure)
        self.assertEqual([bar.section for bar in mapped.bars], [0, 1, 1, 1])
        self.assertTrue(mapped.bars[0].ends_section)

    def test_structure_bar_count_is_independent_of_lyric_line_count(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 100,
                "time_signature": "4/4",
                "sections": [
                    {"id": "verse", "type": "verse", "bars": 2, "chords": []},
                    {"id": "chorus", "type": "chorus", "bars": 2, "chords": []},
                ],
            }
        )
        mapped = apply_song_structure(parse_text("one\ntwo\nthree\nfour\nfive\nsix"), structure)
        self.assertEqual(len(mapped.bars), 4)
        self.assertEqual([bar.section for bar in mapped.bars], [0, 0, 1, 1])


if __name__ == "__main__":
    unittest.main()

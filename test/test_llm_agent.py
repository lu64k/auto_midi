from __future__ import annotations

import unittest

from auto_midi.drum_execution import LLMDrumExecutionAgent
from auto_midi.drum_feel import LLMDrumFeelAgent
from auto_midi.llm_client import _parse_json_content
from auto_midi.section_config import parse_section_config
from auto_midi.song_structure import parse_song_structure


class FakeClient:
    def complete_json(self, system_prompt: str, user_prompt: str, seed: int):
        return {
            "sections": [
                {
                    "section_id": "verse_1",
                    "section_type": "verse",
                    "groove": "classic_rock",
                    "description": "stable backbeat",
                    "energy": 0.4,
                    "density": 0.35,
                    "backbeat_strength": 0.9,
                    "syncopation": 0.2,
                    "swing": 0.0,
                    "variation": 0.15,
                    "fill_level": 0.1,
                    "crash_usage": "section_entry_only",
                    "dropout": 0.05,
                    "chord_context": [["E"], ["B"]],
                    "allowed_voices": [],
                    "required_voices": ["snare"],
                }
            ]
        }


class ExecutionFakeClient:
    def complete_json(self, system_prompt: str, user_prompt: str, seed: int):
        return {
            "sections": [
                {
                    "name": "verse_1",
                    "type": "verse",
                    "bars": 2,
                    "intensity_start": 35,
                    "intensity_end": 45,
                    "density_start": 0.3,
                    "density_end": 0.4,
                    "fill": 10,
                    "fill_mode": "section_end",
                    "allowed": [],
                    "required": ["snare"],
                    "dna_overrides": {"backbeat_weight": 0.9},
                }
            ]
        }


class SongPlanFakeClient:
    def complete_json(self, system_prompt: str, user_prompt: str, seed: int):
        return {
            "structure": {
                "title": "demo",
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [
                    {
                        "id": "verse1",
                        "type": "verse",
                        "bars": 8,
                        "chords": ["E", "B", "C#m", "A"],
                    }
                ],
            },
            "feels": [
                {
                    "section_id": "verse1",
                    "section_type": "verse",
                    "groove": "classic_rock",
                    "description": "restrained verse that builds toward the chorus",
                }
            ],
        }


class SlashChordFakeClient:
    def complete_json(self, system_prompt: str, user_prompt: str, seed: int):
        return {
            "structure": {
                "title": "slash",
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [
                    {"id": "verse1", "type": "verse", "bars": 4, "chords": ["C", "G", "E", "A", "Fm"]}
                ],
            },
            "feels": [
                {
                    "section_id": "verse1",
                    "section_type": "verse",
                    "description": "verse",
                    "chord_context": ["C/G", "E", "A", "Fm"],
                }
            ],
        }


class LLMTests(unittest.TestCase):
    def test_parses_fenced_json(self) -> None:
        self.assertEqual(_parse_json_content("```json\n{\"sections\": []}\n```"), {"sections": []})

    def test_execution_voice_aliases_are_normalized(self) -> None:
        config = parse_section_config(
            {"sections": [{"name": "intro", "bars": 4, "allowed": [], "required": ["hi-hat"]}]}
        )[0]
        self.assertEqual(config.required_voices, ("closed_hat",))

    def test_agent_validates_model_output(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [{"id": "verse_1", "type": "verse", "bars": 2, "chords": [["E"], ["B"]]}],
            }
        )
        feel = LLMDrumFeelAgent(FakeClient()).generate(structure, "rock", "classic_rock", seed=7)[0]
        self.assertEqual(feel.source, "llm")
        self.assertEqual(feel.required_voices, ("snare",))

    def test_execution_agent_validates_and_normalizes_model_output(self) -> None:
        structure = parse_song_structure(
            {
                "bpm": 120,
                "time_signature": "4/4",
                "sections": [{"id": "verse_1", "type": "verse", "bars": 2, "chords": [["E"], ["B"]]}],
            }
        )
        feel = LLMDrumFeelAgent(FakeClient()).generate(structure, "rock", "classic_rock", seed=7)
        config = LLMDrumExecutionAgent(ExecutionFakeClient()).generate(structure, feel, seed=7)[0]
        self.assertEqual(config.name, "verse_1")
        self.assertEqual(config.chord_bars, (("E",), ("B",)))
        self.assertEqual(config.required_voices, ("snare",))

    def test_song_plan_repeats_short_chord_progression(self) -> None:
        structure, feels = LLMDrumFeelAgent(SongPlanFakeClient()).generate_from_requirements(
            "verse 8 bars: E B C#m A",
            120,
            "4/4",
            "rock",
            "classic_rock",
            7,
        )
        self.assertEqual(len(structure.sections[0].chord_bars), 8)
        self.assertEqual(structure.sections[0].chord_bars[4], ("E",))
        self.assertEqual(feels[0].description, "restrained verse that builds toward the chorus")

    def test_song_plan_restores_authored_slash_chord(self) -> None:
        structure, feels = LLMDrumFeelAgent(SlashChordFakeClient()).generate_from_requirements(
            "verse 4 bars, chords C/G-E-A-Fm",
            120,
            "4/4",
            "rock",
            "classic_rock",
            7,
        )
        self.assertEqual(structure.sections[0].chord_bars, (("C/G",), ("E",), ("A",), ("Fm",)))
        self.assertEqual(feels[0].chord_context, (("C/G",), ("E",), ("A",), ("Fm",)))


if __name__ == "__main__":
    unittest.main()

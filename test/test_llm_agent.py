from __future__ import annotations

import unittest

from auto_midi.drum_feel import LLMDrumFeelAgent
from auto_midi.llm_client import _parse_json_content
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


class LLMTests(unittest.TestCase):
    def test_parses_fenced_json(self) -> None:
        self.assertEqual(_parse_json_content("```json\n{\"sections\": []}\n```"), {"sections": []})

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


if __name__ == "__main__":
    unittest.main()

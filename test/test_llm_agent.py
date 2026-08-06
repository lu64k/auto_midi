from __future__ import annotations

import unittest

from auto_midi.drum_execution import LLMDrumExecutionAgent, validate_execution_routing
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
    def __init__(self):
        self.system_prompt = ""
        self.user_prompt = ""

    def complete_json(self, system_prompt: str, user_prompt: str, seed: int):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        routed = "## Live catalog and constraints" in system_prompt
        payload = {
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
                    "voice_placements": {"snare": "section_start"},
                    "groove": "classic_rock" if routed else "sparse_rock",
                    "cymbal_role": "closed_hat_quarters",
                    "intensity_curve": [{"bar": 1, "value": 35}, {"bar": 2, "value": 45}],
                    "dna_overrides": {"backbeat_weight": 0.9},
                }
            ]
        }
        if routed:
            payload["routing"] = {
                "style": "rock",
                "global_groove": "classic_rock",
                "style_source": "ui_locked",
                "groove_source": "ui_locked",
                "confidence": 1.0,
                "reason": "UI locked both routing levels",
                "section_override_reasons": {},
            }
        return payload


class SongPlanFakeClient:
    def __init__(self):
        self.system_prompt = ""

    def complete_json(self, system_prompt: str, user_prompt: str, seed: int):
        self.system_prompt = system_prompt
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
        client = ExecutionFakeClient()
        config = LLMDrumExecutionAgent(client).generate(structure, feel, seed=7)[0]
        self.assertEqual(config.name, "verse_1")
        self.assertEqual(config.chord_bars, (("E",), ("B",)))
        self.assertEqual(config.required_voices, ("snare",))
        self.assertEqual(config.voice_placements, {"snare": "section_start"})
        self.assertEqual(config.groove, "sparse_rock")
        self.assertEqual(config.cymbal_role, "closed_hat_quarters")
        self.assertIn("whole section", client.system_prompt)
        self.assertIn("voice_placements", client.system_prompt)

    def test_execution_plan_receives_selected_style_groove_boundary(self) -> None:
        client = ExecutionFakeClient()
        LLMDrumExecutionAgent(client).generate_from_plan_payload(
            {"structure": {"sections": []}, "feels": []},
            seed=7,
            preset="rock",
            groove="classic_rock",
        )
        self.assertIn('"selected_style": "rock"', client.user_prompt)
        self.assertIn('"selected_global_groove": "classic_rock"', client.user_prompt)
        self.assertIn('"sparse_rock"', client.system_prompt)
        self.assertIn("Prefer one groove for the whole song", client.system_prompt)

    def test_locked_groove_rejects_section_variation(self) -> None:
        payload = {
            "routing": {
                "style": "rock", "global_groove": "classic_rock",
                "confidence": 1, "reason": "locked", "section_override_reasons": {},
            },
            "sections": [],
        }
        configs = parse_section_config({
            "sections": [{"name": "chorus", "bars": 4, "groove": "driving_rock"}]
        })
        with self.assertRaisesRegex(ValueError, "locked UI groove"):
            validate_execution_routing(payload, configs, "rock", "classic_rock")

    def test_unexplained_groove_override_is_rejected(self) -> None:
        payload = {
            "routing": {
                "style": "rock", "global_groove": "classic_rock",
                "confidence": 0.8, "reason": "rock", "section_override_reasons": {},
            },
            "sections": [],
        }
        configs = parse_section_config({
            "sections": [{"name": "bridge", "bars": 4, "groove": "half_time_rock"}]
        })
        with self.assertRaisesRegex(ValueError, "require rhythm-based reasons"):
            validate_execution_routing(payload, configs, "rock", "free")

    def test_song_plan_repeats_short_chord_progression(self) -> None:
        client = SongPlanFakeClient()
        structure, feels = LLMDrumFeelAgent(client).generate_from_requirements(
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
        for voice in (
            "kick", "rim", "snare", "clap", "low_tom", "mid_tom",
            "closed_hat", "open_hat", "crash", "ride",
        ):
            self.assertIn(voice, client.system_prompt)

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

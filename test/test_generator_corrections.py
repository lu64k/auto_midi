from __future__ import annotations

import random
import unittest

from auto_midi.drummer_dna import generate_dna
from auto_midi.pattern_generator import generate_events, should_fill
from auto_midi.section_config import SectionConfig, parse_section_config
from auto_midi.text_parser import parse_text


def _bars(count: int, prefix: str = "bar") -> str:
    return "\n".join(f"{prefix} {index}" for index in range(1, count + 1))


class AlwaysTrigger:
    def random(self) -> float:
        return 0.0


class GeneratorCorrectionTests(unittest.TestCase):
    def _dna(self, text_map, seed: int = 7):
        return generate_dna(
            text_map, random.Random(seed), 40, 50, 20, 20,
            preset="rock", groove="classic_rock",
        )

    def test_required_voice_is_section_level_not_every_bar(self) -> None:
        text_map = parse_text(_bars(8))
        config = SectionConfig(name="outro", bars=8, required_voices=("crash",), fill_mode="none")
        events = generate_events(text_map, self._dna(text_map), random.Random(7), 50, 0, (config,), "4/4")
        crashes = [event for event in events if event.voice == "crash"]
        self.assertEqual(len(crashes), 1)
        self.assertEqual((crashes[0].bar, crashes[0].step), (0, 0))

    def test_section_end_placement_puts_one_crash_at_final_step(self) -> None:
        text_map = parse_text(_bars(8))
        config = SectionConfig(
            name="outro",
            bars=8,
            required_voices=("crash",),
            voice_placements={"crash": "section_end"},
            fill_mode="none",
        )
        events = generate_events(text_map, self._dna(text_map), random.Random(7), 50, 0, (config,), "4/4")
        crashes = [event for event in events if event.voice == "crash"]
        self.assertEqual([(event.bar, event.step) for event in crashes], [(7, 15)])

    def test_last_two_bars_means_exactly_last_two(self) -> None:
        text_map = parse_text(_bars(8))
        config = SectionConfig(name="chorus", bars=8, fill=100, fill_mode="last_2_bars")
        dna = self._dna(text_map)
        triggered = [
            should_fill(bar, dna, AlwaysTrigger(), 100, config, index / 7)
            for index, bar in enumerate(text_map.bars)
        ]
        self.assertEqual(triggered, [False, False, False, False, False, False, True, True])

    def test_low_density_reduces_rock_skeleton(self) -> None:
        text_map = parse_text(_bars(16))
        dna = self._dna(text_map)
        low = SectionConfig(
            name="outro", bars=16, density_start=0.05, density_end=0.05,
            groove="classic_rock", fill_mode="none",
        )
        high = SectionConfig(
            name="chorus", bars=16, density_start=0.70, density_end=0.70,
            groove="classic_rock", fill_mode="none",
        )
        low_events = generate_events(text_map, dna, random.Random(11), 40, 0, (low,), "4/4")
        high_events = generate_events(text_map, dna, random.Random(11), 40, 0, (high,), "4/4")
        self.assertLess(len(low_events), len(high_events) * 0.65)

    def test_cymbal_role_generates_continuous_ride_without_required_hack(self) -> None:
        text_map = parse_text(_bars(4))
        config = SectionConfig(
            name="prechorus", bars=4, allowed_voices=("ride",),
            cymbal_role="ride_eighths", fill_mode="none",
        )
        events = generate_events(text_map, self._dna(text_map), random.Random(3), 40, 0, (config,), "4/4")
        self.assertEqual({event.voice for event in events}, {"ride"})
        self.assertEqual(len(events), 32)

    def test_curves_can_rise_then_fall(self) -> None:
        text_map = parse_text(_bars(4))
        config = SectionConfig(
            name="chorus", bars=4, allowed_voices=("ride",),
            cymbal_role="ride_quarters", fill_mode="none",
            intensity_curve=((1, 20), (3, 80), (4, 10)),
            density_curve=((1, 0.3), (3, 0.7), (4, 0.2)),
        )
        events = generate_events(text_map, self._dna(text_map), random.Random(5), 40, 0, (config,), "4/4")
        averages = [
            sum(event.velocity for event in events if event.bar == bar) / 4
            for bar in range(4)
        ]
        self.assertGreater(averages[2], averages[0])
        self.assertGreater(averages[2], averages[3])

    def test_extended_execution_schema_parses_and_validates(self) -> None:
        config = parse_section_config(
            {
                "sections": [{
                    "name": "outro", "bars": 8,
                    "allowed": ["kick", "crash"], "required": ["crash"],
                    "voice_placements": {"crash": "section_end"},
                    "groove": "post_rock_release", "cymbal_role": "none",
                    "intensity_curve": [{"bar": 1, "value": 20}, {"bar": 8, "value": 5}],
                    "density_curve": [{"bar": 1, "value": 0.15}, {"bar": 8, "value": 0.03}],
                }]
            }
        )[0]
        self.assertEqual(config.voice_placements, {"crash": "section_end"})
        self.assertEqual(config.groove, "post_rock_release")
        self.assertEqual(config.intensity_curve[-1], (8, 5.0))

    def test_shanshu_regression_outro_is_sparse_and_crash_is_not_repeated(self) -> None:
        text_map = parse_text("\n\n".join(_bars(8, name) for name in ("v1", "pre", "v2", "chorus", "outro")))
        configs = (
            SectionConfig("verse1", 8, 15, 30, 0.2, 0.3, 20, "last_bar", required_voices=("kick", "snare", "closed_hat")),
            SectionConfig("prechorus", 8, 35, 30, 0.35, 0.3, 20, "section_end", required_voices=("kick", "snare", "ride", "closed_hat")),
            SectionConfig("verse2", 8, 30, 40, 0.25, 0.35, 25, "last_bar", required_voices=("kick", "snare", "closed_hat")),
            SectionConfig("chorus", 8, 50, 35, 0.5, 0.4, 50, "last_2_bars", required_voices=("kick", "snare", "ride", "crash")),
            SectionConfig("outro", 8, 10, 5, 0.1, 0.05, 0, "none", required_voices=("kick", "snare", "closed_hat", "crash")),
        )
        events = generate_events(text_map, self._dna(text_map), random.Random(7), 50, 20, configs, "4/4")
        chorus = [event for event in events if 24 <= event.bar < 32]
        outro = [event for event in events if 32 <= event.bar < 40]
        self.assertLess(len(outro), len(chorus))
        self.assertEqual(sum(event.voice == "crash" for event in outro), 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from auto_midi.groove import grooves_for_style
from auto_midi.groove_routing_skill import build_routing_skill_context
from auto_midi.rock_patterns import rock_pattern
from auto_midi.style_catalog import DEFAULT_CATALOG_PATH, GrooveCatalogProvider


class StyleCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "drum_styles.json"
        self.payload = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
        self.path.write_text(json.dumps(self.payload), encoding="utf-8")
        self.warnings: list[str] = []
        self.provider = GrooveCatalogProvider(self.path, self.warnings.append)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _add_style(self) -> None:
        updated = deepcopy(self.payload)
        updated["version"] = 2
        updated["styles"]["test_wave"] = {
            "identity": "test-only live style",
            "default_groove": "test_pulse",
            "dna_bounds": {"pulse": [8, 8]},
            "grooves": {
                "test_pulse": {
                    "identity": "test-only live groove",
                    "energy_neutral": True,
                    "profile": {
                        "skeleton_strength": 0.7,
                        "backbeat_variation": 0.2,
                        "ornament_amount": 0.2
                    },
                    "anchor": "strong_one",
                    "pulse": 8,
                    "meters": ["4/4"],
                    "pattern": {
                        "kick_steps": [0, 8],
                        "snare_steps": [4, 12],
                        "hat_steps": [0, 4, 8, 12],
                        "swing_ratio": 0.0
                    }
                }
            }
        }
        self.path.write_text(json.dumps(updated), encoding="utf-8")

    def test_provider_hot_reloads_new_style_without_restart(self) -> None:
        first = self.provider.get()
        self._add_style()
        second = self.provider.get()
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertIn("test_wave", second.styles)

    def test_invalid_update_keeps_last_known_good_catalog(self) -> None:
        first = self.provider.get()
        self.path.write_text('{"version": 2, "styles": {}}', encoding="utf-8")
        second = self.provider.get()
        self.assertIs(first, second)
        self.assertTrue(self.warnings)

    def test_skill_and_groove_views_share_live_catalog(self) -> None:
        self.provider.get()
        self._add_style()
        with patch("auto_midi.style_catalog.CATALOG", self.provider):
            self.assertEqual(grooves_for_style("test_wave"), ("test_pulse",))
            context = build_routing_skill_context("test_wave", "free")
            pattern = rock_pattern("test_pulse")
        self.assertIn('"test_pulse"', context)
        self.assertIn('"catalog_version":2', context)
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.kick_steps, (0, 8))

    def test_ui_refresh_sees_new_style_without_restart(self) -> None:
        first_hash = self.provider.get().content_hash
        self._add_style()
        from gradio_app import _catalog_controls_update

        with patch("auto_midi.style_catalog.CATALOG", self.provider):
            current_hash, style_update, groove_update = _catalog_controls_update(
                first_hash,
                "test_wave",
                "test_pulse",
            )
        style_values = {choice[1] if isinstance(choice, tuple) else choice for choice in style_update.choices}
        groove_values = {choice[1] if isinstance(choice, tuple) else choice for choice in groove_update.choices}
        self.assertNotEqual(first_hash, current_hash)
        self.assertIn("test_wave", style_values)
        self.assertEqual(style_update.value, "test_wave")
        self.assertIn("free", groove_values)
        self.assertIn("test_pulse", groove_values)


if __name__ == "__main__":
    unittest.main()

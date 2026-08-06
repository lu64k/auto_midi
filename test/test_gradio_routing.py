from __future__ import annotations

import unittest

from auto_midi.drum_execution import ExecutionRouting
from auto_midi.section_config import SectionConfig
from gradio_app import _resolve_routing_controls


def _routing() -> ExecutionRouting:
    return ExecutionRouting(
        style="rock",
        global_groove="classic_rock",
        style_source="ui_locked",
        groove_source="agent_routed",
        confidence=0.9,
        reason="stable rock",
        section_override_reasons={},
        catalog_version=1,
        catalog_hash="sha256:test",
    )


class GradioRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.configs = (SectionConfig("verse", 4, groove="classic_rock"),)

    def test_checked_uses_execution_routing(self) -> None:
        style, groove, configs, authority, warning = _resolve_routing_controls(
            self.configs, _routing(), "rock", "sparse_rock", True
        )
        self.assertEqual((style, groove, authority), ("rock", "classic_rock", "execution_config"))
        self.assertEqual(configs[0].groove, "classic_rock")
        self.assertIsNone(warning)

    def test_unchecked_uses_fixed_ui_groove(self) -> None:
        style, groove, configs, authority, _ = _resolve_routing_controls(
            self.configs, _routing(), "rock", "sparse_rock", False
        )
        self.assertEqual((style, groove, authority), ("rock", "sparse_rock", "ui"))
        self.assertEqual(configs[0].groove, "sparse_rock")

    def test_ui_free_uses_execution_resolution(self) -> None:
        style, groove, _, authority, _ = _resolve_routing_controls(
            self.configs, _routing(), "free", "free", False
        )
        self.assertEqual((style, groove, authority), ("rock", "classic_rock", "ui"))

    def test_checked_old_config_falls_back_with_warning(self) -> None:
        style, groove, _, authority, warning = _resolve_routing_controls(
            self.configs, None, "rock", "classic_rock", True
        )
        self.assertEqual((style, groove, authority), ("rock", "classic_rock", "ui"))
        self.assertIn("no routing metadata", warning)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from auto_midi.work_history import WorkHistoryStore


class WorkHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = WorkHistoryStore(
            Path(self.temporary.name),
            now_provider=lambda: datetime(2026, 8, 6, 15, 30, 0),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_blank_title_uses_date_and_collision_suffix(self) -> None:
        first = self.store.save("", "lyrics one", "", "")
        second = self.store.save("", "lyrics two", "", "")
        self.assertEqual(first.title, "2026-08-06")
        self.assertEqual(second.title, "2026-08-06-02")

    def test_same_title_loads_and_overwrites_in_place(self) -> None:
        original = self.store.save("Demo", "lyrics", "feel one", "execution one")
        updated = self.store.save(" demo ", "new lyrics", "feel two", "execution two")
        self.assertEqual(updated.record_id, original.record_id)
        self.assertEqual(updated.title, "Demo")
        loaded = self.store.load("DEMO")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.lyrics_and_requirements, "new lyrics")
        self.assertEqual(loaded.feel_plan_json, "feel two")
        self.assertEqual(loaded.execution_config_json, "execution two")
        self.assertEqual(len(self.store.list_records()), 1)

    def test_invalid_json_text_is_preserved_verbatim(self) -> None:
        record = self.store.save("raw", "brief", "{unfinished", "not-json")
        loaded = self.store.load(record.title)
        self.assertEqual(loaded.feel_plan_json, "{unfinished")
        self.assertEqual(loaded.execution_config_json, "not-json")


if __name__ == "__main__":
    unittest.main()

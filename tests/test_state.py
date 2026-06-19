import unittest

from musicrec import state
from tests.base import Base


class TestState(Base):
    def test_watermark_roundtrip(self):
        self.assertIsNone(state.get_watermark(self.cfg))            # none yet
        state.set_watermark(self.cfg, "2026-06-17T08:00:00")
        self.assertEqual(state.get_watermark(self.cfg), "2026-06-17T08:00:00")

    def test_added_query(self):
        self.assertEqual(state.added_query(None), "")               # first run -> whole library
        self.assertEqual(state.added_query("2026-06-17T08:00:00"), "added:2026-06-17T08:00:00..")

    def test_corrupt_state_is_none(self):
        self.cfg.beetsdir.mkdir(parents=True, exist_ok=True)
        (self.cfg.beetsdir / "musicrec-state.json").write_text("{ not json")
        self.assertIsNone(state.get_watermark(self.cfg))            # fail soft, not crash


if __name__ == "__main__":
    unittest.main()

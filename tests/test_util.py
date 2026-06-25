import unittest
from unittest import mock

from gbc.util import length_secs, prune_empty_dirs, skip_on_error
from tests.base import Base


class TestSkipOnError(unittest.TestCase):
    """Per-item isolation: one raising item is logged + swallowed, the loop keeps going."""

    def test_isolates_bad_item_and_continues(self):
        log = mock.MagicMock()
        processed = []
        for x in [1, 2, 3]:
            with skip_on_error(log, "pass", x):
                if x == 2:
                    raise ValueError("boom")
                processed.append(x)
        self.assertEqual(processed, [1, 3])              # item 2 skipped, 1 and 3 still processed
        log.warning.assert_called_once()                 # the failure was logged, not silent

    def test_continue_inside_guard_still_works(self):
        log = mock.MagicMock()
        seen = []
        for x in [1, 2, 3]:
            with skip_on_error(log, "pass", x):
                if x == 2:
                    continue                             # explicit early-skip, not an error
                seen.append(x)
        self.assertEqual(seen, [1, 3])
        log.warning.assert_not_called()                  # a clean `continue` is not a failure


class TestLengthSecs(unittest.TestCase):
    """Parse beets' `$length` ('M:SS' / 'H:MM:SS') -> whole seconds (used to read durations via `beet ls`)."""

    def test_m_ss(self):
        self.assertEqual(length_secs("2:06"), 126)
        self.assertEqual(length_secs("0:10"), 10)
        self.assertEqual(length_secs("1:30"), 90)
        self.assertEqual(length_secs("73:20"), 4400)        # minutes can exceed 59 in beets' format

    def test_h_mm_ss(self):
        self.assertEqual(length_secs("1:02:03"), 3723)

    def test_bare_and_empty_and_garbage(self):
        self.assertEqual(length_secs("225"), 225)           # bare seconds
        self.assertEqual(length_secs(""), 0)
        self.assertEqual(length_secs("   "), 0)
        self.assertEqual(length_secs("N/A"), 0)             # unparseable -> 0, never raises


class TestPruneEmptyDirs(Base):
    """prune_empty_dirs is called after verify/albumdedup/qa move files out of clean -- a destructive dir op
    that had zero direct coverage. Lock: only-empty removed, audio dirs kept, root always preserved."""

    def test_removes_empty_keeps_nonempty_and_root(self):
        root = self.tmp / "clean"
        (root / "Artist" / "Empty Album (2020)").mkdir(parents=True)   # fully empty shell (all tracks moved out)
        full = root / "Artist2" / "Full Album (2021)"
        full.mkdir(parents=True)
        (full / "01 - track.flac").write_bytes(b"x")
        prune_empty_dirs(root)
        self.assertFalse((root / "Artist" / "Empty Album (2020)").exists())   # empty shell pruned
        self.assertFalse((root / "Artist").exists())                          # then its now-empty parent, bottom-up
        self.assertTrue(full.exists())                                        # dir holding audio kept
        self.assertTrue((root / "Artist2").exists())
        self.assertTrue(root.exists())                                        # root itself never removed

    def test_root_preserved_even_when_empty(self):
        root = self.tmp / "emptyroot"
        root.mkdir()
        prune_empty_dirs(root)
        self.assertTrue(root.exists())                                        # mindepth 1: root is never a target

    def test_nested_empty_chain_fully_removed(self):
        root = self.tmp / "clean"
        (root / "a" / "b" / "c").mkdir(parents=True)
        prune_empty_dirs(root)
        self.assertFalse((root / "a").exists())                               # whole empty chain gone
        self.assertTrue(root.exists())


if __name__ == "__main__":
    unittest.main()

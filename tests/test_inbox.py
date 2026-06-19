import unittest

from gbc.lock import import_lock
from gbc.passes import inbox
from tests.base import Base


class TestInboxGate(Base):
    def test_has_new_reads_the_plan(self):
        self.assertTrue(inbox.has_new("Skipped 5 paths.\nAlbum: /x/Y\n  /x/Y/01.flac\n"))
        self.assertTrue(inbox.has_new("Singleton: /x/track.mp3\n"))
        self.assertFalse(inbox.has_new("Skipped 5 paths.\n"))     # the old gate bug: nothing new
        self.assertFalse(inbox.has_new(""))

    def test_inbox_nothing_new_exits_clean(self):
        (self.cfg.src / "Some Folder").mkdir(parents=True)
        (self.cfg.src / "Some Folder" / "a.flac").write_text("x")
        self.cfg.beet = self.fake_beet(stderr="Skipped 1 paths.\n")   # --pretend plan on STDERR, nothing new
        self.assertEqual(inbox.run(self.cfg), 0)
        self.assertFalse((self.cfg.beetsdir / "gbc-state.json").exists())   # pipeline never ran

    def test_inbox_bows_out_when_locked(self):
        (self.cfg.src / "f").mkdir(parents=True)
        self.cfg.beet = self.fake_beet(stderr="Album: /x\n")
        with import_lock(self.cfg, blocking=True) as got:
            self.assertTrue(got)
            self.assertEqual(inbox.run(self.cfg), 0)                  # busy -> exits without importing
        self.assertFalse((self.cfg.beetsdir / "gbc-state.json").exists())


if __name__ == "__main__":
    unittest.main()

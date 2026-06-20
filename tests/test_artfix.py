import unittest
from unittest import mock

from gbc import artfix
from tests.base import Base


class TestArtfix(Base):
    def test_strips_only_broken_wma(self):
        src = self.cfg.src
        (src / "Album").mkdir(parents=True)
        (src / "Album" / "a.wma").write_bytes(b"x")       # broken art -> stripped
        (src / "Album" / "b.wma").write_bytes(b"x")       # valid art  -> left alone
        (src / "Album" / "c.mp3").write_bytes(b"x")       # not WMA    -> never touched (even if "broken")
        broken = {str(src / "Album" / "a.wma"), str(src / "Album" / "c.mp3")}
        stripped = []
        with mock.patch.object(artfix, "_broken_art", lambda p: p in broken), \
             mock.patch.object(artfix, "_strip_wma", lambda p: stripped.append(p) or True):
            n = artfix.run(self.cfg)
        self.assertEqual(n, 1)                            # only a.wma (broken AND .wma)
        self.assertEqual(stripped, [str(src / "Album" / "a.wma")])

    def test_cache_skips_unchanged_on_second_run(self):
        self.cfg.src.mkdir(parents=True)
        (self.cfg.src / "b.wma").write_bytes(b"x")    # a clean WMA
        calls = []
        with mock.patch.object(artfix, "_broken_art", lambda p: calls.append(p) or False), \
             mock.patch.object(artfix, "_strip_wma", lambda p: True):
            artfix.run(self.cfg)                      # 1st run parses b.wma
            artfix.run(self.cfg)                      # 2nd run: unchanged -> cached -> skipped
        self.assertEqual(calls, [str(self.cfg.src / "b.wma")])   # parsed once, not twice

    def test_skips_when_deps_absent(self):
        with mock.patch.object(artfix.importlib.util, "find_spec", lambda name: None):
            self.assertEqual(artfix.run(self.cfg), 0)     # no mediafile/mutagen -> guard skipped, no crash


if __name__ == "__main__":
    unittest.main()

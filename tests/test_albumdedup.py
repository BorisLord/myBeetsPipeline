import unittest
from unittest import mock

from gbc.passes import albumdedup
from tests.base import Base

SEP = albumdedup.SEP


class TestAlbumDedup(Base):
    def _make(self, specs):
        """specs: [(album_id, album_title, mb_albumid, bitrate, [durations])] -- all share albumartist
        'Artist'. Creates the folders + returns the fake `beet ls` text (8 SEP-joined fields)."""
        lines = []
        for aid, title, mb, br, durs in specs:
            folder = self.cfg.clean / "Artist" / title
            folder.mkdir(parents=True)
            for i, dur in enumerate(durs):
                f = folder / f"{i:02d}.m4a"
                f.write_bytes(b"x")
                lines.append(SEP.join([aid, "Artist", title, "2001", dur, br, mb, str(f)]))
        return "\n".join(lines)

    def _run(self, text):
        calls = []

        def fake_run_beet(cfg, args, **k):
            calls.append(args)
            return (0, text) if args and args[0] == "ls" else (0, "")

        with mock.patch.object(albumdedup, "run_beet", fake_run_beet), \
             mock.patch.object(albumdedup, "backup_db", lambda *a, **k: None):
            n = albumdedup.run(self.cfg)
        return n, calls

    def test_keeps_musicbrainz_quarantines_discogs(self):
        durs = ["3:00", "4:00", "5:00"]
        n, calls = self._run(self._make([
            ("1", "Power: The Essential", "12345", "256kbps", durs),       # Discogs (numeric mb id)
            ("2", "Power - The Essential", "a1b2-c3d4", "256kbps", durs),   # MusicBrainz (uuid)
        ]))
        self.assertEqual(n, 1)
        self.assertTrue((self.cfg.clean / "Artist" / "Power - The Essential").is_dir())     # MB kept
        self.assertFalse((self.cfg.clean / "Artist" / "Power: The Essential").exists())     # Discogs out
        self.assertTrue((self.cfg.dump / "duplicates" / "Artist" / "Power: The Essential").is_dir())
        self.assertTrue(any(a[:3] == ["remove", "-a", "-f"] and "id:1" in a for a in calls))

    def test_prefers_higher_bitrate_when_same_source(self):
        durs = ["3:00", "4:00", "5:00"]
        n, _ = self._run(self._make([
            ("1", "Hits Vol 1", "x1-y2", "128kbps", durs),        # MB, low bitrate
            ("2", "Hits, Vol. 1", "x3-y4", "320kbps", durs),      # MB, high bitrate -> kept
        ]))
        self.assertEqual(n, 1)
        self.assertTrue((self.cfg.clean / "Artist" / "Hits, Vol. 1").is_dir())
        self.assertFalse((self.cfg.clean / "Artist" / "Hits Vol 1").exists())

    def test_tolerant_match_different_rip(self):
        # same album, DIFFERENT rip: each track drifts a few seconds (<= TOL) + close title -> deduped
        n, _ = self._run(self._make([
            ("1", "Dark Side", "11", "256kbps", ["3:00", "4:00", "5:00"]),        # Discogs
            ("2", "The Dark Side", "a-b", "256kbps", ["3:05", "4:08", "5:10"]),   # MB, +5/8/10s drift
        ]))
        self.assertEqual(n, 1)
        self.assertTrue((self.cfg.clean / "Artist" / "The Dark Side").is_dir())   # MB kept
        self.assertFalse((self.cfg.clean / "Artist" / "Dark Side").exists())

    def test_different_title_not_merged(self):
        # same artist, same track count, durations within TOL, but UNRELATED titles -> NOT a duplicate
        n, calls = self._run(self._make([
            ("1", "Help", "11", "256kbps", ["2:00", "2:10", "2:20"]),
            ("2", "Beatles for Sale", "a-b", "256kbps", ["2:02", "2:12", "2:22"]),
        ]))
        self.assertEqual(n, 0)
        self.assertTrue((self.cfg.clean / "Artist" / "Help").is_dir())
        self.assertTrue((self.cfg.clean / "Artist" / "Beatles for Sale").is_dir())
        self.assertFalse(any(a and a[0] == "remove" for a in calls))

    def test_different_volume_not_merged(self):
        # same artist, same count, durations within TOL, similar title BUT different volume number -> NOT a dup
        n, calls = self._run(self._make([
            ("1", "Nova Classics Four", "11", "256kbps", ["3:00", "4:00", "5:00"]),
            ("2", "Nova Classics Seven", "a-b", "256kbps", ["3:05", "4:08", "5:10"]),
        ]))
        self.assertEqual(n, 0)
        self.assertTrue((self.cfg.clean / "Artist" / "Nova Classics Four").is_dir())
        self.assertTrue((self.cfg.clean / "Artist" / "Nova Classics Seven").is_dir())
        self.assertFalse(any(a and a[0] == "remove" for a in calls))

    def test_distinct_albums_not_touched(self):
        n, calls = self._run(self._make([
            ("1", "Album One", "11", "256kbps", ["3:00", "4:00", "5:00"]),
            ("2", "Album Two", "22", "256kbps", ["3:30", "4:30", "5:30"]),   # different durations + title
        ]))
        self.assertEqual(n, 0)
        self.assertTrue((self.cfg.clean / "Artist" / "Album One").is_dir())
        self.assertTrue((self.cfg.clean / "Artist" / "Album Two").is_dir())
        self.assertFalse(any(a and a[0] == "remove" for a in calls))

    def test_too_few_tracks_skipped(self):
        n, _ = self._run(self._make([
            ("1", "Single Disc", "11", "256kbps", ["3:00", "4:00"]),    # 2 tracks < MINTRACKS
            ("2", "Single MB", "a-b", "256kbps", ["3:00", "4:00"]),
        ]))
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()

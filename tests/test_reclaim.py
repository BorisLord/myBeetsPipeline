import json
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from gbc import sidecars
from gbc.beetscfg import BeetsImport
from gbc.passes import reclaim
from tests.base import Base


def _fake_dur(p):
    """'NN - ...': NN*10 seconds (so ffprobe is never spawned in tests)."""
    name = Path(p).name
    return int(name[:2]) * 10 if name[:2].isdigit() else 0


class TestReclaim(Base):
    def _src_album(self, name, tracks):
        d = self.cfg.src / name
        d.mkdir(parents=True)
        for t in tracks:
            (d / f"{t} - s.flac").write_text("x")
        return d

    def _build_db(self, albums):
        """albums: {clean_subdir: [(filename, length)]} -> create library.db, return {path: ...} for verdicts."""
        self.cfg.beetsdir.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.cfg.library)
        con.execute("CREATE TABLE items (path TEXT, length REAL)")
        paths = []
        for sub, items in albums.items():
            for fn, length in items:
                p = str(self.cfg.clean / sub / fn)
                con.execute("INSERT INTO items VALUES (?,?)", (p, float(length)))
                paths.append((sub, p))
        con.commit()
        con.close()
        return paths

    def _write_verdicts(self, mapping):
        (self.cfg.beetsdir / "gbc-verify-verdicts.json").write_text(json.dumps(mapping), encoding="utf-8")

    def _scenario(self):
        good = self._src_album("AlbumGood", ["01", "02", "03"])        # 10,20,30 -> all ok -> RECLAIM
        rare = self._src_album("AlbumRare", ["04", "05"])              # 40,50 -> one rare -> keep
        part = self._src_album("AlbumPartial", ["06", "07", "08"])     # 60,70,80, but clean has 2 -> keep
        ambig = self._src_album("AlbumAmbig", ["09"])                  # 90 -> matches two clean albums -> keep
        self._build_db({
            "Good": [("01.flac", 10), ("02.flac", 20), ("03.flac", 30)],
            "Rare": [("04.flac", 40), ("05.flac", 50)],
            "Partial": [("06.flac", 60), ("07.flac", 70)],            # only 2 of 3 imported
            "AmbigX": [("x.flac", 90)],
            "AmbigY": [("y.flac", 90)],
        })
        self._write_verdicts({
            str(self.cfg.clean / "Good" / "01.flac"): "ok",
            str(self.cfg.clean / "Good" / "02.flac"): "ok",
            str(self.cfg.clean / "Good" / "03.flac"): "ok",
            str(self.cfg.clean / "Rare" / "04.flac"): "ok",
            str(self.cfg.clean / "Rare" / "05.flac"): "rare",
            str(self.cfg.clean / "Partial" / "06.flac"): "ok",
            str(self.cfg.clean / "Partial" / "07.flac"): "ok",
            str(self.cfg.clean / "AmbigX" / "x.flac"): "ok",
            str(self.cfg.clean / "AmbigY" / "y.flac"): "ok",
        })
        return good, rare, part, ambig

    def test_reclaims_only_fully_verified_albums(self):
        good, rare, part, ambig = self._scenario()
        with mock.patch.object(reclaim.beetscfg, "read_import", lambda c: BeetsImport(copy=True)), \
             mock.patch.object(sidecars, "dur", _fake_dur):
            moved = reclaim.run(self.cfg)
        self.assertEqual(moved, 1)
        self.assertFalse(good.exists())                                  # all-ok album reclaimed
        self.assertTrue((self.cfg.dump / "AlbumGood").exists())          # -> quarantine
        self.assertTrue(rare.exists())                                   # a rare track -> kept
        self.assertTrue(part.exists())                                   # count mismatch -> kept
        self.assertTrue(ambig.exists())                                  # ambiguous match -> kept

    def test_move_mode_reclaims_nothing(self):
        good, *_ = self._scenario()
        with mock.patch.object(reclaim.beetscfg, "read_import", lambda c: BeetsImport(move=True)), \
             mock.patch.object(sidecars, "dur", _fake_dur):
            moved = reclaim.run(self.cfg)
        self.assertEqual(moved, 0)
        self.assertTrue(good.exists())                                   # source consumed by beets -> never reclaim

    def test_no_library_is_noop(self):
        with mock.patch.object(reclaim.beetscfg, "read_import", lambda c: BeetsImport(copy=True)):
            self.assertEqual(reclaim.run(self.cfg), 0)


if __name__ == "__main__":
    unittest.main()

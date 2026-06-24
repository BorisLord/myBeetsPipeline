import json
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
    def setUp(self):
        super().setUp()
        self._ls_text = ""            # the `beet ls` output reclaim now reads natively (set by _build_lib)

    def _src_album(self, name, tracks):
        d = self.cfg.src / name
        d.mkdir(parents=True)
        for t in tracks:
            (d / f"{t} - s.flac").write_text("x")
        return d

    def _build_lib(self, albums):
        """albums: {clean_subdir: [(filename, length_secs)]} -> the `beet ls -f '$id\\t$path\\t$length\\t...'`
        text reclaim parses (length rendered as beets does, 'M:SS'). Touches library.db so reclaim.run's
        exists() guard passes. Returns {(subdir, filename): id_str} for keying verdicts by item id."""
        self.cfg.beetsdir.mkdir(parents=True, exist_ok=True)
        self.cfg.library.write_bytes(b"")           # presence only; data comes from the mocked `beet ls`
        lines, ids, nid = [], {}, 0
        for sub, items in albums.items():
            for fn, length in items:
                nid += 1
                p = str(self.cfg.clean / sub / fn)
                lines.append(f"{nid}\t{p}\t{length // 60}:{length % 60:02d}\tTigran\t{sub}\t2015")
                ids[(sub, fn)] = str(nid)
        self._ls_text = "\n".join(lines)
        return ids

    def _reclaim(self, import_mode):
        with mock.patch.object(reclaim.beetscfg, "read_import", lambda c: import_mode), \
             mock.patch.object(reclaim, "run_beet", lambda cfg, a, **k: (0, self._ls_text)), \
             mock.patch.object(sidecars, "dur", _fake_dur):
            return reclaim.run(self.cfg)

    def _scenario(self):
        good = self._src_album("AlbumGood", ["01", "02", "03"])        # 10,20,30 -> all ok -> RECLAIM
        rare = self._src_album("AlbumRare", ["04", "05"])              # 40,50 -> one rare -> keep
        part = self._src_album("AlbumPartial", ["06", "07", "08"])     # 60,70,80, but clean has 2 -> keep
        ambig = self._src_album("AlbumAmbig", ["09"])                  # 90 -> matches two clean albums -> keep
        ids = self._build_lib({
            "Good": [("01.flac", 10), ("02.flac", 20), ("03.flac", 30)],
            "Rare": [("04.flac", 40), ("05.flac", 50)],
            "Partial": [("06.flac", 60), ("07.flac", 70)],            # only 2 of 3 imported
            "AmbigX": [("x.flac", 90)],
            "AmbigY": [("y.flac", 90)],
        })
        self._write_verdicts({
            ids[("Good", "01.flac")]: "ok",
            ids[("Good", "02.flac")]: "ok",
            ids[("Good", "03.flac")]: "ok",
            ids[("Rare", "04.flac")]: "ok",
            ids[("Rare", "05.flac")]: "rare",
            ids[("Partial", "06.flac")]: "ok",
            ids[("Partial", "07.flac")]: "ok",
            ids[("AmbigX", "x.flac")]: "ok",
            ids[("AmbigY", "y.flac")]: "ok",
        })
        return good, rare, part, ambig

    def _write_verdicts(self, mapping):
        (self.cfg.beetsdir / "gbc-verify-verdicts.json").write_text(json.dumps(mapping), encoding="utf-8")

    def test_reclaims_only_fully_verified_albums(self):
        good, rare, part, ambig = self._scenario()
        moved = self._reclaim(BeetsImport(copy=True))
        self.assertEqual(moved, 1)
        self.assertFalse(good.exists())                                  # all-ok album reclaimed
        self.assertTrue((self.cfg.dump / "reclaimed" / "Tigran" / "Good (2015)").exists())   # reason/artist/album
        self.assertTrue(rare.exists())                                   # a rare track -> kept
        self.assertTrue(part.exists())                                   # count mismatch -> kept
        self.assertTrue(ambig.exists())                                  # ambiguous match -> kept

    def test_move_mode_reclaims_nothing(self):
        good, *_ = self._scenario()
        moved = self._reclaim(BeetsImport(move=True))
        self.assertEqual(moved, 0)
        self.assertTrue(good.exists())                                   # source consumed by beets -> never reclaim

    def test_duplicate_source_folders_neither_reclaimed(self):
        # two identical-duration source folders but ONE clean copy -> can't tell which was copied -> keep both
        d1 = self._src_album("DupA", ["01", "02"])      # durs 10,20
        d2 = self._src_album("DupB", ["01", "02"])      # same multiset
        ids = self._build_lib({"Clean": [("01.flac", 10), ("02.flac", 20)]})
        self._write_verdicts({ids[("Clean", fn)]: "ok" for fn in ("01.flac", "02.flac")})
        moved = self._reclaim(BeetsImport(copy=True))
        self.assertEqual(moved, 0)
        self.assertTrue(d1.exists() and d2.exists())    # both kept in source (clean backs at most one reclaim)

    def test_unreadable_track_skips_whole_folder(self):
        # a folder with an unprobeable file -> shrunk multiset must NOT be matched against a smaller clean album
        alb = self._src_album("Partial", ["01", "02"])  # durs 10,20
        (alb / "bad.flac").write_text("x")              # _fake_dur -> 0 (probe failure); folder now has 3 files
        ids = self._build_lib({"Clean": [("01.flac", 10), ("02.flac", 20)]})  # would match SHRUNK [10,20] sans guard
        self._write_verdicts({ids[("Clean", fn)]: "ok" for fn in ("01.flac", "02.flac")})
        moved = self._reclaim(BeetsImport(copy=True))
        self.assertEqual(moved, 0)                       # unmeasurable folder never reclaimed
        self.assertTrue(alb.exists())

    def test_floor_vs_round_within_tolerance_still_matches(self):
        # native `beet ls` floors $length to M:SS while source durs round -> <=1s drift, absorbed by TOL.
        good = self._src_album("AlbumGood", ["01", "02"])               # _fake_dur -> 10, 20 (rounded)
        # clean lengths rendered one second short (as a floor would) -> 0:09, 0:19 -> still within TOL of 10,20
        self.cfg.beetsdir.mkdir(parents=True, exist_ok=True)
        self.cfg.library.write_bytes(b"")
        self._ls_text = "\n".join([
            f"1\t{self.cfg.clean / 'Good' / '01.flac'}\t0:09\tTigran\tGood\t2015",
            f"2\t{self.cfg.clean / 'Good' / '02.flac'}\t0:19\tTigran\tGood\t2015",
        ])
        self._write_verdicts({"1": "ok", "2": "ok"})
        self.assertEqual(self._reclaim(BeetsImport(copy=True)), 1)      # 9~10, 19~20 -> still bijective match
        self.assertFalse(good.exists())

    def test_no_library_is_noop(self):
        self.assertEqual(self._reclaim(BeetsImport(copy=True)), 0)      # no library.db -> early return


if __name__ == "__main__":
    unittest.main()

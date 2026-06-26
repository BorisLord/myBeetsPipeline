import json
import unittest
from pathlib import Path
from unittest import mock

from gbc.passes import verify
from tests.base import Base


class TestVerify(Base):
    def _items(self, specs):
        """specs: [(stem, mbid)] -> create the files (so stat() works) + return the fake `beet ls` text
        (8 fields: $id $path $mb_trackid $albumartist $album $year $artist $title)."""
        lines = []
        for i, (stem, mbid) in enumerate(specs, 1):
            (self.tmp / f"{stem}.m4a").write_bytes(b"x")
            p = self.tmp / f"{stem}.m4a"
            lines.append(f"{i}{verify.SEP}{p}{verify.SEP}{mbid}{verify.SEP}TestArtist{verify.SEP}TestAlbum"
                         f"{verify.SEP}2001{verify.SEP}TestArtist{verify.SEP}TestTitle")
        return "\n".join(lines)

    def test_quarantines_only_conclusive_imposters(self):
        text = self._items([("a", "mbA"), ("b", "mbB"), ("c", "mbC"), ("d", "mbD")])
        # a: genuine match -> kept ; b: audio confidently matches a DIFFERENT recording -> IMPOSTER ;
        # c: throttled -> inconclusive (kept) ; d: no-match but NO confident alternative -> kept (unprovable)
        fv = {"a": ("ok", True, None), "b": ("ok", False, ("Den Harrow", "OtherSong", 0.95)),
              "c": ("error", False, None), "d": ("ok", False, None)}
        with mock.patch.object(verify, "_acoustid_available", lambda: True), \
             mock.patch.object(verify, "run_beet", lambda *a, **k: (0, text)), \
             mock.patch.object(verify, "_file_verdict", lambda p, m: fv[Path(p).stem]):
            n = verify.run(self.cfg)
        self.assertEqual(n, 1)                                    # only the real imposter (b)
        self.assertFalse((self.tmp / "b.m4a").exists())           # imposter moved out of "clean"
        self.assertTrue((self.cfg.dump / "imposters" / "TestArtist" / "TestAlbum (2001)" / "b.m4a").exists())
        for stem in ("a", "c", "d"):
            self.assertTrue((self.tmp / f"{stem}.m4a").exists())  # genuine / inconclusive kept

    def test_skips_cleanly_without_pyacoustid(self):
        with mock.patch.object(verify, "_acoustid_available", lambda: False):
            self.assertEqual(verify.run(self.cfg), 0)

    def test_imposter_cached_inconclusive_not_cached(self):
        text = self._items([("b", "mbB"), ("c", "mbC")])      # b -> imposter, c -> inconclusive (throttled)
        fv = {"b": ("ok", False, ("Den Harrow", "OtherSong", 0.95)), "c": ("error", False, None)}
        with mock.patch.object(verify, "_acoustid_available", lambda: True), \
             mock.patch.object(verify, "run_beet", lambda *a, **k: (0, text)), \
             mock.patch.object(verify, "_file_verdict", lambda p, m: fv[Path(p).stem]):
            verify.run(self.cfg)
        cache = json.loads((self.cfg.beetsdir / "gbc-verify-cache.json").read_text())
        self.assertEqual(list(cache.values()), ["imposter"])  # imposter cached; inconclusive deliberately not

    def test_file_verdict_detects_strong_mismatch(self):
        """Audio matches a DIFFERENT recording with high confidence -> mismatch (artist, title, score)."""
        import acoustid
        resp = {"status": "ok", "results": [{"score": 0.93, "recordings": [
            {"id": "mbOther", "title": "These Boots (radio edit)", "artists": [{"name": "Barcode Brothers"}]}]}]}
        with mock.patch.object(acoustid, "fingerprint_file", lambda p: (190, "FP")), \
             mock.patch.object(acoustid, "lookup", lambda *a, **k: resp):
            status, present, mismatch = verify._file_verdict("x.m4a", "mbTagged")
        self.assertEqual((status, present), ("ok", False))
        self.assertEqual(mismatch, ("Barcode Brothers", "These Boots (radio edit)", 0.93))

    def test_file_verdict_present_has_no_mismatch(self):
        """Tagged recording IS among the matches -> present, no mismatch flagged."""
        import acoustid
        resp = {"status": "ok", "results": [{"score": 0.95, "recordings": [
            {"id": "mbTagged", "title": "T", "artists": [{"name": "A"}]}]}]}
        with mock.patch.object(acoustid, "fingerprint_file", lambda p: (190, "FP")), \
             mock.patch.object(acoustid, "lookup", lambda *a, **k: resp):
            _, present, mismatch = verify._file_verdict("x.m4a", "mbTagged")
        self.assertTrue(present)
        self.assertIsNone(mismatch)

    def test_file_verdict_weak_other_not_flagged(self):
        """A weak (<MISMATCH_SCORE) match to another recording is NOT a mismatch (conservative refute bar)."""
        import acoustid
        resp = {"status": "ok", "results": [{"score": 0.6, "recordings": [
            {"id": "mbOther", "title": "T", "artists": [{"name": "A"}]}]}]}
        with mock.patch.object(acoustid, "fingerprint_file", lambda p: (190, "FP")), \
             mock.patch.object(acoustid, "lookup", lambda *a, **k: resp):
            status, present, mismatch = verify._file_verdict("x.m4a", "mbTagged")
        self.assertEqual((status, present, mismatch), ("ok", False, None))

    def test_confident_mismatch_quarantined(self):
        """A confident DIFFERENT-recording match (different artist, not a sibling) is positive evidence -> the
        track is quarantined as an imposter and an IMPOSTER warning is logged."""
        text = self._items([("a", "mbA")])
        fv = {"a": ("ok", False, ("Barcode Brothers", "Some Other Song", 0.93))}
        with mock.patch.object(verify, "_acoustid_available", lambda: True), \
             mock.patch.object(verify, "run_beet", lambda *a, **k: (0, text)), \
             mock.patch.object(verify, "_file_verdict", lambda p, m: fv[Path(p).stem]), \
             self.assertLogs("gbc", "WARNING") as cm:
            n = verify.run(self.cfg)
        self.assertEqual(n, 1)                                   # quarantined (audio is a different recording)
        self.assertFalse((self.tmp / "a.m4a").exists())          # moved out of clean
        self.assertTrue(any("IMPOSTER" in m and "Barcode Brothers" in m for m in cm.output))

    def test_sibling_recording_kept_even_if_known(self):
        """Zenzile case: audio confidently matches the SAME title with an overlapping artist credit (a sibling
        recording id) -> verdict 'ok', kept + no warning, EVEN THOUGH the tagged id is known to AcoustID."""
        text = self._items([("a", "mbA")])
        fv = {"a": ("ok", False, ("TestArtist Crew", "TestTitle", 0.99))}   # same title, credit-variant artist
        with mock.patch.object(verify, "_acoustid_available", lambda: True), \
             mock.patch.object(verify, "run_beet", lambda *a, **k: (0, text)), \
             mock.patch.object(verify, "_file_verdict", lambda p, m: fv[Path(p).stem]), \
             self.assertNoLogs("gbc", "WARNING"):
            n = verify.run(self.cfg)
        self.assertEqual(n, 0)                                   # NOT quarantined (same-song sibling)
        self.assertTrue((self.tmp / "a.m4a").exists())

    def test_same_title_unrelated_artist_still_imposter(self):
        """UB40 'Don't Break My Heart' vs Den Harrow's: same title but no shared artist token -> real imposter."""
        text = self._items([("a", "mbA")])
        fv = {"a": ("ok", False, ("Den Harrow", "TestTitle", 0.97))}        # same title, unrelated artist
        with mock.patch.object(verify, "_acoustid_available", lambda: True), \
             mock.patch.object(verify, "run_beet", lambda *a, **k: (0, text)), \
             mock.patch.object(verify, "_file_verdict", lambda p, m: fv[Path(p).stem]):
            n = verify.run(self.cfg)
        self.assertEqual(n, 1)                                   # genuine imposter quarantined

    def test_imposter_db_remove_issued_after_move(self):
        """stale-DB regression: after quarantining an imposter the lib entry MUST be dropped by id, so beets
        never points at the moved file."""
        text = self._items([("b", "mbB")])              # single item -> id 1
        calls = []
        with mock.patch.object(verify, "_acoustid_available", lambda: True), \
             mock.patch.object(verify, "run_beet", lambda cfg, a, **k: calls.append(a) or (0, text)), \
             mock.patch.object(verify, "_file_verdict", lambda p, m: ("ok", False, ("X Artist", "Y Song", 0.95))):
            n = verify.run(self.cfg)
        self.assertEqual(n, 1)
        self.assertIn(["remove", "-f", "id:1"], calls)   # DB-sync by id

    def test_failed_move_leaves_file_and_no_db_remove(self):
        """safe_move fails -> imposter stays in clean and NO lib-remove (no stale entry pointing at it)."""
        text = self._items([("b", "mbB")])
        calls = []
        with mock.patch.object(verify, "_acoustid_available", lambda: True), \
             mock.patch.object(verify, "run_beet", lambda cfg, a, **k: calls.append(a) or (0, text)), \
             mock.patch.object(verify, "_file_verdict", lambda p, m: ("ok", False, ("X Artist", "Y Song", 0.95))), \
             mock.patch.object(verify, "safe_move", lambda *a, **k: False):
            n = verify.run(self.cfg)
        self.assertEqual(n, 0)
        self.assertTrue((self.tmp / "b.m4a").exists())   # kept in clean
        self.assertFalse(any(a[0] == "remove" for a in calls))

    def test_same_song_helper(self):
        # same title + overlapping artist credit -> sibling (the false-imposter cases)
        self.assertTrue(verify._same_song("Zenzile, High Tone", "The Source",
                                          "Zenzile Meets High Tone", "The Source"))
        self.assertTrue(verify._same_song("Timmi Magic, PGS", "Tell Me", "Timmi Magic & PSG", "Tell Me"))
        # same title but unrelated artist -> NOT a sibling (genuine imposter)
        self.assertFalse(verify._same_song("Den Harrow", "Don't Break My Heart", "UB40", "Don't Break My Heart"))
        # different title -> not a sibling even with the same artist
        self.assertFalse(verify._same_song("TestArtist", "Other Title", "TestArtist", "TestTitle"))


if __name__ == "__main__":
    unittest.main()

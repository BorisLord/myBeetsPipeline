import unittest
from unittest import mock

from musicrec import state
from musicrec.passes import enrich, import_, pipeline, qa, replaygain
from tests.base import Base


class TestPipelineScope(Base):
    def test_scope_follows_watermark(self):
        seen = {}

        def fake_enrich(c, query=""):
            seen["enrich"] = query
            return 0

        def fake_rg(c, query=""):
            seen["rg"] = query
            return 0

        def fake_qa(c, scope=""):
            seen["qa"] = scope
            return 0

        with mock.patch.object(import_, "run", lambda c, src=None: 0), \
             mock.patch.object(enrich, "run", fake_enrich), \
             mock.patch.object(replaygain, "run", fake_rg), \
             mock.patch.object(qa, "run", fake_qa):
            # first run: no watermark -> whole library (empty scope), watermark set afterwards
            self.assertEqual(pipeline.run(self.cfg), 0)
            self.assertEqual((seen["enrich"], seen["rg"], seen["qa"]), ("", "", ""))
            wm = state.get_watermark(self.cfg)
            self.assertTrue(wm)

            # second run: scope = added:<watermark>..
            pipeline.run(self.cfg)
            self.assertTrue(seen["enrich"].startswith("added:"))
            self.assertTrue(seen["enrich"].endswith(".."))
            self.assertEqual(seen["qa"], seen["enrich"])

            # full mode ignores the watermark
            pipeline.run(self.cfg, full=True)
            self.assertEqual(seen["enrich"], "")

    def test_failed_pass_does_not_advance_watermark(self):
        # enrich errors -> pipeline reports failure and the watermark stays unset (next run retries)
        with mock.patch.object(import_, "run", lambda c, src=None: 0), \
             mock.patch.object(enrich, "run", lambda c, query="": 1), \
             mock.patch.object(replaygain, "run", lambda c, query="": 0), \
             mock.patch.object(qa, "run", lambda c, scope="": 0):
            rc = pipeline.run(self.cfg)
        self.assertNotEqual(rc, 0)
        self.assertIsNone(state.get_watermark(self.cfg))

    def test_failed_import_aborts_before_enrich(self):
        reached = {"enrich": False}

        def fake_enrich(c, query=""):
            reached["enrich"] = True
            return 0

        with mock.patch.object(import_, "run", lambda c, src=None: 2), \
             mock.patch.object(enrich, "run", fake_enrich):
            rc = pipeline.run(self.cfg)
        self.assertEqual(rc, 2)
        self.assertFalse(reached["enrich"])            # import failure aborts the pipeline
        self.assertIsNone(state.get_watermark(self.cfg))


if __name__ == "__main__":
    unittest.main()

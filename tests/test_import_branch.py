import unittest
from unittest import mock

from gbc.beetscfg import BeetsImport
from gbc.passes import import_
from tests.base import Base


class TestImportBranch(Base):
    """gbc adapts to beets' import op: source-mutating passes run ONLY when beets consumes the source."""

    def setUp(self):
        super().setUp()
        self.cfg.src.mkdir(parents=True, exist_ok=True)
        self.calls = []

    def _run_with(self, bi):
        def rec(name):
            return lambda *a, **k: self.calls.append(name)
        with mock.patch.object(import_.beetscfg, "read_import", lambda c: bi), \
             mock.patch.object(import_.artfix, "run", lambda *a, **k: 0), \
             mock.patch.object(import_, "_beet_import", lambda *a: self.calls.append("import") or 0), \
             mock.patch.object(import_, "dedup", rec("dedup")), \
             mock.patch.object(import_.sidecars, "snapshot", lambda *a, **k: self.calls.append("snapshot") or 0), \
             mock.patch.object(import_.sidecars, "apply", rec("apply")), \
             mock.patch.object(import_.sidecars, "prune_shells", rec("prune")), \
             mock.patch.object(import_, "prune_empty_dirs", rec("prune_empty")), \
             mock.patch.object(import_, "backup_db", lambda *a, **k: None), \
             mock.patch.object(import_, "count_items", lambda *a, **k: 0):
            import_.run(self.cfg)
        return self.calls

    def test_move_runs_source_mutating_passes(self):
        calls = self._run_with(BeetsImport(move=True))
        self.assertEqual(calls, ["dedup", "snapshot", "import", "apply", "prune", "prune_empty"])

    def test_copy_keeps_source_read_only(self):
        calls = self._run_with(BeetsImport(copy=True))
        self.assertEqual(calls, ["import"])              # nothing touches the source

    def test_symlink_also_keeps_source_read_only(self):
        self.assertEqual(self._run_with(BeetsImport(link=True)), ["import"])


if __name__ == "__main__":
    unittest.main()

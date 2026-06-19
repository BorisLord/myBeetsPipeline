import unittest

from gbc.lock import import_lock
from tests.base import Base


class TestLock(Base):
    def test_mutual_exclusion(self):
        with import_lock(self.cfg, blocking=True) as got1:
            self.assertTrue(got1)
            with import_lock(self.cfg, blocking=False) as got2:   # busy -> non-blocking bows out
                self.assertFalse(got2)
        with import_lock(self.cfg, blocking=False) as got3:       # released -> available again
            self.assertTrue(got3)


if __name__ == "__main__":
    unittest.main()

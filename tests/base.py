"""Shared test base: a tmp dir + a Config pointing into it + a fake `beet` factory.
Run the suite with:  python -m unittest discover -s tests -t .  (or `mise run test`)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from gbc.config import Config


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gbc-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = Config(
            beet="beet",
            beetsdir=self.tmp / "beets",
            src=self.tmp / "source",
            clean=self.tmp / "clean",
            dump=self.tmp / "dump",
            log_dir=self.tmp / "logs",
        )

    def fake_beet(self, stdout="", stderr="", code=0):
        """Write a fake `beet` executable that emits given stdout/stderr and exits with code."""
        script = self.tmp / "fakebeet"
        body = "#!/usr/bin/env python3\nimport sys\n"
        if stdout:
            body += f"sys.stdout.write({stdout!r})\n"
        if stderr:
            body += f"sys.stderr.write({stderr!r})\n"
        body += f"sys.exit({code})\n"
        script.write_text(body)
        script.chmod(0o755)
        return str(script)

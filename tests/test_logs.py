import logging
import unittest

from musicrec import logs
from tests.base import Base


def _reset():
    lg = logging.getLogger("musicrec")
    for h in lg.handlers:
        h.close()
    lg.handlers.clear()
    lg.filters.clear()
    logs._configured = False


class TestLogs(Base):
    def setUp(self):
        super().setUp()
        _reset()
        self.addCleanup(_reset)

    def test_single_tagged_file_and_append(self):
        logs.configure(self.tmp, "ab12", console=False)
        logs.get_logger("import").info("hello world")
        logs.get_logger("enrich").info("second pass")
        text = (self.tmp / "musicrec.log").read_text()
        self.assertIn("run=ab12  [import]  INFO  hello world", text)
        self.assertIn("run=ab12  [enrich]  INFO  second pass", text)
        self.assertEqual(list(self.tmp.glob("*.log")), [self.tmp / "musicrec.log"])  # NOT one file per pass

        _reset()                                      # a later run APPENDS (never truncates)
        logs.configure(self.tmp, "cd34", console=False)
        logs.get_logger("qa").info("later line")
        text2 = (self.tmp / "musicrec.log").read_text()
        self.assertIn("hello world", text2)
        self.assertIn("run=cd34  [qa]  INFO  later line", text2)


if __name__ == "__main__":
    unittest.main()

import unittest

from gbc import anomaly
from tests.base import Base


def row(*fields):
    # id, albumartist, artist, album, title, length, bitrate, singleton, comp, albumtype, mb_trackid
    return "@@@".join(fields)


ROWS = [
    row("1", "The Beatles", "The Beatles", "Abbey Road", "Come Together", "4:20", "900", "F", "F", "album", "a"),
    row("2", "the beatles", "the beatles", "Abbey Road", "Something", "3:00", "900", "F", "F", "album", "b"),
    row("3", "VA", "X", "http://spam.example", "T", "3:00", "200", "F", "F", "album", "c"),
    row("4", "", "Some Artist", "", "Loose", "2:30", "128", "True", "F", "", "d"),
    row("5", "Pink Floyd", "Pink Floyd", "The Wall - CD2", "Hey You", "4:00", "900", "F", "F", "album", "e"),
]


class TestAnomaly(Base):
    def test_categories(self):
        tsv = self.tmp / "in.tsv"
        tsv.write_text("\n".join(ROWS) + "\n")
        out = self.tmp / "out"
        counts = anomaly.scan(str(tsv), str(out))
        self.assertGreaterEqual(counts["artist_variant"], 1)   # The Beatles / the beatles
        self.assertGreaterEqual(counts["junk_album"], 1)       # url album
        self.assertGreaterEqual(counts["orphan"], 1)           # singleton, no album
        self.assertGreaterEqual(counts["disc_in_name"], 1)     # "- CD2"
        self.assertTrue((out / "loose_dup.tsv").exists())      # every category gets a TSV, even empty


if __name__ == "__main__":
    unittest.main()

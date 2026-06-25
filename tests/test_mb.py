import unittest
from unittest import mock

from gbc import mb


class TestMb(unittest.TestCase):
    def test_release_recordings_collects_all_media(self):
        data = {"media": [
            {"tracks": [{"recording": {"id": "r1"}}, {"recording": {"id": "r2"}}]},
            {"tracks": [{"recording": {"id": "r3"}}]},                                  # second disc
        ]}
        with mock.patch.object(mb, "get", lambda p: data), \
             mock.patch.object(mb.time, "sleep", lambda *a: None):
            self.assertEqual(mb.release_recordings("rel1"), frozenset({"r1", "r2", "r3"}))

    def test_release_recordings_empty_on_fetch_error(self):
        with mock.patch.object(mb, "get", mock.Mock(side_effect=OSError("boom"))):
            self.assertEqual(mb.release_recordings("rel1"), frozenset())

    def test_get_retries_transient_then_succeeds(self):
        import urllib.error

        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": 1}'

        calls = {"n": 0}

        def fake_urlopen(req, timeout=0):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.URLError("503-ish transient")    # MB rate-limiter hiccup
            return _Resp()

        with mock.patch.object(mb.urllib.request, "urlopen", fake_urlopen), \
             mock.patch.object(mb.time, "sleep", lambda *a: None):
            self.assertEqual(mb.get("release/x"), {"ok": 1})
        self.assertEqual(calls["n"], 3)                              # two failures retried, third succeeded


if __name__ == "__main__":
    unittest.main()

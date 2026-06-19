import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from musicrec import config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="musicrec-cfg-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_defaults_when_no_config(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.tmp)}), \
             mock.patch.object(config, "REPO_ROOT", self.tmp):
            os.environ.pop("MUSICREC_CONFIG", None)            # restored by patch.dict
            cfg = config.load()
        base = self.tmp / "Music" / "beetsPipeline"
        self.assertEqual(cfg.src, base / "source")
        self.assertEqual(cfg.clean, base / "clean")
        self.assertEqual(cfg.dump, base / "quarantine")
        self.assertEqual(cfg.log_dir, base / "logs")
        self.assertEqual(cfg.beet, "beet")

    def test_sources_config_env(self):
        cenv = self.tmp / "config.env"
        cenv.write_text(
            'MUSIC_SRC="${MUSIC_SRC:-/x/src}"\n'
            'MUSIC_CLEAN="${MUSIC_CLEAN:-/x/clean}"\n'
            'MUSIC_DUMP="${MUSIC_DUMP:-/x/dump}"\n'
            'LOG_DIR="${LOG_DIR:-$(dirname "$MUSIC_CLEAN")/logs}"\n'
        )
        with mock.patch.dict(os.environ, {"MUSICREC_CONFIG": str(cenv)}):
            cfg = config.load()
        self.assertEqual(str(cfg.src), "/x/src")
        self.assertEqual(str(cfg.clean), "/x/clean")
        self.assertEqual(str(cfg.log_dir), "/x/logs")          # dirname(/x/clean)/logs

    def test_env_overrides_config_env(self):
        cenv = self.tmp / "config.env"
        cenv.write_text('MUSIC_CLEAN="${MUSIC_CLEAN:-/default/clean}"\n')
        with mock.patch.dict(os.environ, {"MUSICREC_CONFIG": str(cenv), "MUSIC_CLEAN": "/overridden/clean"}):
            cfg = config.load()
        self.assertEqual(str(cfg.clean), "/overridden/clean")  # ${VAR:-...} keeps the env value


if __name__ == "__main__":
    unittest.main()

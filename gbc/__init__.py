"""gbc — recover a chaotic music library into a clean album library (beets-driven).

One core, several front doors: `run` (manual) and `inbox` (cron) call the SAME pipeline;
only the trigger and the scope differ, never the logic.
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("golden-beets-config")   # single source of truth = pyproject (no manual drift)
except PackageNotFoundError:                        # source tree without an install
    __version__ = "0.0.0+unknown"

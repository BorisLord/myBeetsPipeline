"""Pre-import scrub-crash guard -- runs automatically before every import.

A WMA/ASF file carrying an embedded image with mime_type=None makes beets' `scrub` plugin crash, and a
single such file aborts the WHOLE `beet import`. This pass scans the source for those files and strips the
broken image (via mutagen). Removing it is safe: it's junk metadata, and real art is re-fetched by
`fetchart` during import. SURGICAL -- only WMA that actually carry a mime=None image are written; valid
art and every other file are left untouched. This is the ONE source write gbc makes even in copy/preserve
mode (a necessary repair, not a move). Best-effort: missing mediafile/mutagen just skips the guard.
"""
import importlib.util
import json
import os
from pathlib import Path

from .config import Config
from .logs import get_logger

CACHE = "gbc-artfix-cache.json"


def _broken_art(path) -> bool:
    """True if the file carries an embedded image whose mime_type is None (the scrub crasher)."""
    import mediafile
    try:
        return any(getattr(img, "mime_type", None) is None for img in (mediafile.MediaFile(path).images or []))
    except Exception:
        return False


def _strip_wma(path) -> bool:
    """Remove every embedded picture from a WMA/ASF file via mutagen. Returns True on success."""
    from mutagen.asf import ASF
    try:
        a = ASF(path)
        for k in [k for k in a if "Picture" in k]:
            del a[k]
        a.save()
        return True
    except Exception:
        return False


def run(cfg: Config, src=None, log=None) -> int:
    """Strip mime=None embedded art from source WMA so scrub can't crash the import. Returns count stripped.
    Cached by path+mtime+size (BEETSDIR/gbc-artfix-cache.json): a clean WMA is parsed once, never re-parsed
    while unchanged -- so repeat/cron runs only examine new or modified files, not the whole folder again."""
    log = log or get_logger("artfix")
    root = str(src) if src else str(cfg.src)
    if importlib.util.find_spec("mediafile") is None or importlib.util.find_spec("mutagen") is None:
        log.warning("mediafile/mutagen absent -> scrub-crash WMA guard skipped")
        return 0
    cpath = cfg.beetsdir / CACHE
    try:
        cache = set(json.loads(cpath.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        cache = set()

    fixed = failed = 0
    for dp, _, files in os.walk(root):
        for fn in files:
            if Path(fn).suffix.lower() != ".wma":
                continue
            p = str(Path(dp) / fn)
            try:
                st = Path(p).stat()
            except OSError:
                continue
            key = f"{int(st.st_mtime)}:{st.st_size}:{p}"
            if key in cache:                       # already examined & unchanged -> skip the costly parse
                continue
            if _broken_art(p):                     # broken -> strip; the file changes, so its key is re-examined
                if _strip_wma(p):                  #   next run (now clean -> then cached)
                    fixed += 1
                    log.info("artfix: stripped mime=None art -> %s", p)
                else:
                    failed += 1
            else:
                cache.add(key)                     # clean WMA, unchanged -> remember, never re-parse it
    cfg.beetsdir.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(sorted(cache)), encoding="utf-8")
    if fixed or failed:
        log.info("=== artfix: %d WMA broken-art stripped (%d unfixable) ===", fixed, failed)
    return fixed

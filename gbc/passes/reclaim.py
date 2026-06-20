"""Reclaim verified source originals -- preserve-mode only (beets copy / reflink / hardlink).

After `beet import` COPIED matched albums into clean and `verify` confirmed each track by AcoustID
fingerprint, a SOURCE album whose every track has a positively-verified ("ok") clean copy is redundant:
the whole source folder is moved to $MUSIC_DUMP (never deleted). PER-ALBUM only -- a folder is reclaimed
solely when ALL its audio is accounted for in clean AND every matched track verified ok, so a
partially-matched or any-track-unverified album stays intact in source for curation.

clean<->source correlation reuses sidecars' proven DURATION-MULTISET match (robust to tag/name rewrites):
a source leaf folder is reclaimed only when exactly ONE clean album has the identical track-length multiset
and the same track count. Multi-disc / nested / ambiguous folders don't map to a single clean album -> they
are conservatively left in source. Verdicts come from the verify pass (BEETSDIR/gbc-verify-verdicts.json),
written fresh each run so stale data can never trigger a reclaim.
"""
import json
import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from .. import beetscfg
from ..config import Config
from ..logs import get_logger
from ..sidecars import AUDIO, durs_of, matches, safe_move

VERDICTS = "gbc-verify-verdicts.json"


def _source_albums(src: str) -> dict[str, list[int]]:
    """Leaf source folders (those directly holding audio) -> sorted track durations."""
    by_dir: dict[str, list[str]] = defaultdict(list)
    for dp, _, files in os.walk(src):
        for fn in files:
            if Path(fn).suffix.lower() in AUDIO:
                by_dir[dp].append(str(Path(dp) / fn))
    out = {}
    for d, paths in by_dir.items():
        ds = durs_of(paths)
        if ds:
            out[d] = ds
    return out


def _clean_albums(db: str, clean_root: str) -> dict[str, dict]:
    """beets items grouped by clean album dir -> {'durs': sorted lengths, 'paths': item paths}."""
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
        rows = con.execute("SELECT path, length FROM items").fetchall()
    out: dict[str, dict] = defaultdict(lambda: {"durs": [], "paths": []})
    for (path, length) in rows:
        p = path.decode("utf-8", "surrogateescape") if isinstance(path, bytes) else path
        pp = Path(p)
        if not pp.is_absolute():                       # beets >=2.10 stores paths relative to the lib root
            pp = Path(clean_root) / pp
        out[str(pp.parent)]["durs"].append(round(length or 0))
        out[str(pp.parent)]["paths"].append(str(pp))
    for v in out.values():
        v["durs"].sort()
    return out


def run(cfg: Config, log=None) -> int:
    """Move fully-verified source albums to quarantine (preserve+independent mode). Returns the count moved."""
    log = log or get_logger("reclaim")
    bi = beetscfg.read_import(cfg)
    if not bi.clean_independent:
        log.info("reclaim skipped: beets import=%s (source consumed, or clean not an independent copy)", bi.label)
        return 0
    if not cfg.library.exists():
        return 0
    try:
        verdicts = json.loads((cfg.beetsdir / VERDICTS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        verdicts = {}

    src_albums = _source_albums(str(cfg.src))
    clean_albums = _clean_albums(str(cfg.library), str(cfg.clean))
    src_root = str(Path(cfg.src).resolve())
    moved = kept = ambig = 0
    for sdir, sdurs in src_albums.items():
        if str(Path(sdir).resolve()) == src_root:      # never move the source root itself
            continue
        cands = [c for c in clean_albums.values()
                 if len(c["paths"]) == len(sdurs) and matches(c["durs"], sdurs)]
        if len(cands) != 1:
            kept += 1
            ambig += len(cands) > 1
            continue
        if not all(verdicts.get(p) == "ok" for p in cands[0]["paths"]):
            kept += 1                                  # a track is imposter / rare / inconclusive -> keep source
            continue
        dest = cfg.dump / Path(sdir).name
        i = 1
        while dest.exists():
            i += 1
            dest = cfg.dump / f"{Path(sdir).name} ({i})"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if safe_move(sdir, dest, log):
            moved += 1
            log.info("RECLAIM verified album: %s -> %s/ (%d track(s) all ok)", Path(sdir).name, dest, len(sdurs))
    log.info("=== reclaim: %d verified source album(s) -> %s; %d kept (%d ambiguous) ===",
             moved, cfg.dump, kept, ambig)
    return moved

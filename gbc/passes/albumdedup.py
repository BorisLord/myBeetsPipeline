"""Pass -- de-duplicate ALBUMS in the CLEAN library.

The same album imported twice from two source copies can be matched to two DIFFERENT releases (e.g. one
MusicBrainz, one Discogs) -> different mb_albumid + a slightly different title -> beets' own
duplicate_action (keyed on mb_albumid) never sees them as duplicates and keeps both. We correlate albums by
CONTENT -- same albumartist + the same track-duration multiset (the technique sidecars/reclaim already use)
-- keep the best copy (MusicBrainz over Discogs, then best bitrate) and move the rest to
quarantine/duplicates (NEVER deleted; library.db backed up first). Runs in BOTH import modes (the
source-side dedup in dedup.py is within-folder, track-level, move-mode only -- it cannot see this).
"""
import re
from collections import defaultdict
from pathlib import Path

from ..beets import run_beet
from ..config import Config
from ..logs import get_logger
from ..sidecars import quarantine_dir, safe_move
from ..util import backup_db

SEP = "\x1f"
MINTRACKS = 3   # >=3 tracks: an exact duration-multiset coincidence between DISTINCT albums is then ~nil


def _secs(s: str) -> int:
    """beets' $length is 'M:SS' (or 'H:MM:SS') -> whole seconds."""
    s = s.strip()
    if not s:
        return 0
    try:
        if ":" in s:
            v = 0.0
            for part in s.split(":"):
                v = v * 60 + float(part)
            return round(v)
        return round(float(s))
    except ValueError:
        return 0


def _is_mb(mb_albumid: str) -> bool:
    return "-" in (mb_albumid or "")   # MusicBrainz album ids are UUIDs; Discogs ids are bare integers


def run(cfg: Config, *, do_apply: bool = True) -> int:
    """Quarantine content-duplicate albums (same artist + same track durations), keeping the best copy.
    Returns the number of duplicate albums moved (would-move count when do_apply=False)."""
    log = get_logger("albumdedup")
    fmt = f"$album_id{SEP}$albumartist{SEP}$album{SEP}$year{SEP}$length{SEP}$bitrate{SEP}$mb_albumid{SEP}$path"
    _, text = run_beet(cfg, ["ls", "-f", fmt], passname="albumdedup", echo_lines=False)

    albums: dict = {}
    for line in text.splitlines():
        p = line.split(SEP)
        if len(p) < 8 or not p[0]:
            continue
        aid, albumartist, album, year, length, bitrate, mb, path = p[:8]
        a = albums.setdefault(aid, {"artist": albumartist, "album": album, "year": year, "mb": mb,
                                    "durs": [], "br": 0, "folder": Path(path).parent})
        a["durs"].append(_secs(length))
        digits = re.sub(r"\D", "", bitrate)
        a["br"] = max(a["br"], int(digits) if digits else 0)

    groups: dict = defaultdict(list)
    for aid, a in albums.items():
        if len(a["durs"]) < MINTRACKS or sum(a["durs"]) <= 0:
            continue
        groups[(a["artist"].casefold(), tuple(sorted(a["durs"])))].append(aid)
    dup_groups = [aids for aids in groups.values() if len(aids) > 1]
    if not dup_groups:
        log.info("=== album dedup: no content-duplicate albums ===")
        return 0
    if do_apply:
        backup_db(cfg, "albumdedup", log)

    moved = 0
    for aids in dup_groups:
        # keeper: MusicBrainz over Discogs, then best bitrate, then lowest album id (deterministic)
        keeper = max(aids, key=lambda i: (_is_mb(albums[i]["mb"]), albums[i]["br"], -int(i)))
        for aid in aids:
            if aid == keeper:
                continue
            a = albums[aid]
            folder = Path(a["folder"])
            if not folder.is_dir():
                continue
            qd = quarantine_dir(cfg.dump, "duplicates", a["artist"])   # duplicates/<Artist>/ ; folder = "Album (Year)"
            dest = qd / folder.name
            n = 1
            while dest.exists():
                n += 1
                dest = qd / f"{folder.name} ({n})"
            if do_apply:
                qd.mkdir(parents=True, exist_ok=True)
            if not do_apply or safe_move(folder, dest, log):
                if do_apply:
                    run_beet(cfg, ["remove", "-a", "-f", f"id:{aid}"], passname="albumdedup", echo_lines=False)
                moved += 1
                log.info("%s dup album: %s - %s -> %s/ (kept '%s')",
                         "DEDUP" if do_apply else "DRY ", a["artist"], a["album"], dest, albums[keeper]["album"])
    log.info("=== album dedup: %d duplicate album(s) -> quarantine/duplicates ===", moved)
    return moved

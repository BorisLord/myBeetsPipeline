"""Pass -- per-track AcoustID fingerprint verification: detect & quarantine IMPOSTER tracks.

An imposter has the right title/duration/tags but its AUDIO is a different recording; album-mode import
trusts the lot and `chroma` gives no penalty to a track it can't identify, so it slips into a "strong" album.
We act ONLY on POSITIVE evidence: the file's own fingerprint CONFIDENTLY matches a DIFFERENT recording than
its tags claim. If AcoustID merely can't confirm the tagged recording (no confident alternative either) the
track is KEPT (unprovable -- intros/short/live/obscure audio AcoustID just can't ID); a same-song sibling /
credit variant is kept too. Inconclusive (rate-limit/timeout) -> left alone. Imposter -> MOVED to $MUSIC_DUMP
(never deleted) + dropped from the lib. Verdicts cached per file.
"""
import importlib.util
import json
import os
import re
import time
from pathlib import Path

from ..beets import run_beet
from ..config import Config
from ..logs import get_logger
from ..sidecars import quarantine_dir, safe_move
from ..util import backup_db, prune_empty_dirs, skip_on_error

APIKEY = os.environ.get("GBC_ACOUSTID_APIKEY", "1vOwZtEn")  # beets' shared key; set your own to avoid throttling
MATCH_SCORE = 0.5   # AcoustID result score above which the file CONFIRMS the tagged recording
MISMATCH_SCORE = 0.9  # higher bar to REFUTE: audio matches a DIFFERENT recording this strongly -> tag likely wrong
RETRIES = 4         # attempts on rate-limit / network error before giving up -> inconclusive
SEP = "\x1f"        # US control char: can't appear in tags/paths and survives str.splitlines() (unlike \x1e)


def _acoustid_available() -> bool:
    return importlib.util.find_spec("acoustid") is not None


def _same_song(m_artist: str, m_title: str, artist: str, title: str) -> bool:
    """The audio confidently matched a DIFFERENT recording id than the tag -- but is it the SAME song under a
    sibling / credit variant (e.g. 'Zenzile, High Tone' vs 'Zenzile Meets High Tone', 'A & B' vs 'A, B')?
    True iff the titles are identical AND the two artist credits share a token. A real wrong-audio that merely
    shares a title (UB40's 'Don't Break My Heart' vs Den Harrow's) still flags -- the artist tokens don't overlap."""
    if re.sub(r"\W+", "", m_title.lower()) != re.sub(r"\W+", "", title.lower()):
        return False
    ta = {t for t in re.split(r"\W+", m_artist.lower()) if len(t) >= 2}
    tb = {t for t in re.split(r"\W+", artist.lower()) if len(t) >= 2}
    return bool(ta & tb)


def _file_verdict(path, mbid):
    """('ok', present, mismatch) once AcoustID answers conclusively, else ('error', False, None). present=True
    when the file's own fingerprint lists the tagged recording -> genuine; False => audio is something else.
    mismatch=(artist, title, score) when the audio matches a DIFFERENT recording >= MISMATCH_SCORE -- the
    positive evidence that flags an imposter."""
    import acoustid
    for attempt in range(RETRIES):
        try:
            dur, fp = acoustid.fingerprint_file(path)
            resp = acoustid.lookup(APIKEY, fp, dur, meta="recordings")
        except acoustid.FingerprintGenerationError:
            return "error", False, None                 # can't fingerprint -> inconclusive
        except acoustid.WebServiceError:
            time.sleep(2 ** attempt)
            continue
        if resp.get("status") != "ok":
            time.sleep(2 ** attempt)
            continue
        results = resp.get("results") or []
        present = any(rec.get("id") == mbid
                      for r in results if (r.get("score") or 0) >= MATCH_SCORE
                      for rec in (r.get("recordings") or []))
        mismatch = None
        if not present:                                 # audio != tag: is it confidently some other known recording?
            for r in results:                           # results are best-score first
                if (r.get("score") or 0) < MISMATCH_SCORE:
                    break                               # sorted desc -> nothing below the bar matters
                for rec in (r.get("recordings") or []):
                    if rec.get("id") == mbid:
                        continue
                    artist = ", ".join(a.get("name", "") for a in (rec.get("artists") or []))
                    title = rec.get("title") or ""
                    if artist or title:
                        mismatch = (artist, title, round(r.get("score") or 0, 2))
                        break
                if mismatch:
                    break
        return "ok", present, mismatch
    return "error", False, None


def run(cfg: Config, scope="") -> int:
    """Flag imposter tracks among items in `scope` (whole library if empty). Returns the imposter count."""
    log = get_logger("verify")
    if not _acoustid_available():
        log.warning("pyacoustid not available -> fingerprint verification skipped")
        return 0
    sc = [scope] if scope else []
    fmt = f"$id{SEP}$path{SEP}$mb_trackid{SEP}$albumartist{SEP}$album{SEP}$year{SEP}$artist{SEP}$title"
    _, text = run_beet(cfg, ["ls", "-f", fmt, "mb_trackid::.", *sc], passname="verify", echo_lines=False)
    rows = [ln.split(SEP, 7) for ln in text.splitlines() if ln.count(SEP) >= 7]

    cpath = cfg.beetsdir / "gbc-verify-cache.json"
    try:
        cache = json.loads(cpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}

    moved, checked, incon, backed = [], 0, 0, False
    mismatches = 0
    for itemid, path, mbid, albumartist, album, year, artist, title in rows:
        try:
            st = Path(path).stat()
        except OSError:
            continue
        key = f"{int(st.st_mtime)}:{st.st_size}:{mbid}"        # re-check only if the file changed
        verdict = cache.get(key)
        if verdict is None:
            status, present, mismatch = _file_verdict(path, mbid)
            if status != "ok":
                incon += 1
                continue                                       # inconclusive -> not cached, retried next run
            sibling = bool(mismatch) and _same_song(mismatch[0], mismatch[1], artist, title)
            if present or sibling:                 # tagged recording present, or a same-song sibling/credit-variant id
                verdict = "ok"
            elif mismatch:                         # audio CONFIDENTLY matches a different recording -> proven imposter
                mismatches += 1
                log.warning("IMPOSTER: %s - %s | audio = %s - %s (%.2f)",
                            artist, title, mismatch[0], mismatch[1], mismatch[2])
                verdict = "imposter"
            else:                                  # tagged id absent but NO confident alternative -> unprovable, KEEP
                verdict = "rare"
            cache[key] = verdict
            checked += 1
        if verdict == "imposter":                              # quarantine, never deleted
            with skip_on_error(log, "verify", path):           # one bad move never loses the run's verdicts
                if not backed:
                    backup_db(cfg, "verify", log)
                    backed = True
                qd = quarantine_dir(cfg.dump, "imposters", albumartist, album, year, fallback=Path(path).parent.name)
                dest = qd / Path(path).name
                i = 1
                while dest.exists():
                    i += 1
                    dest = qd / f"{Path(path).stem} ({i}){Path(path).suffix}"
                qd.mkdir(parents=True, exist_ok=True)
                if safe_move(path, dest, log):                 # move out of clean, then drop the stale lib entry
                    rc, _ = run_beet(cfg, ["remove", "-f", f"id:{itemid}"], passname="verify", echo_lines=False)
                    if rc:
                        log.warning("verify: `beet remove` rc=%d for id:%s -- stale lib entry may remain", rc, itemid)
                    moved.append(path)
                    log.info("QUARANTINE imposter (audio != tagged recording): %s -> %s/", Path(path).name, qd)

    cfg.beetsdir.mkdir(parents=True, exist_ok=True)
    with cpath.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    log.info("=== fingerprint verify: %d check(s), %d imposter(s) quarantined, %d mismatch(es), %d inconclusive ===",
             checked, len(moved), mismatches, incon)
    if moved:
        prune_empty_dirs(cfg.clean)                            # remove album shells left fully empty by quarantine
        log.info("  [IMPOSTER] %d track(s) (audio != tagged recording) moved to %s -- recoverable, never deleted",
                 len(moved), cfg.dump)
    return len(moved)

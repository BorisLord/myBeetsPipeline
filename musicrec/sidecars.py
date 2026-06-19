#!/usr/bin/env python3
"""Carry an album's OFFICIAL sidecars (booklet/cover/back/inlay/scan... + .lrc lyrics) from the source
folder to the matched album in the clean library. Works with import `move: yes`:

  snapshot BEFORE import (source still has its audio) -> apply AFTER the move (copy the leftovers).

Matching is by audio DURATION (robust to tag/name changes), captured pre-move from the source and
compared to the clean album durations in beets' library.db. ffprobe (source) and beets/mutagen (db)
disagree by a few seconds per track, so the match is TOLERANT: same track count + each sorted duration
within TOL seconds. Embedded covers/lyrics already travel inside the files; this rescues loose files only.
READ on source, MOVE into clean (no copy left in source); a file already present in clean is moved to the
quarantine dir instead (never deleted). Durations via ffprobe (ships with ffmpeg) -> no extra Python deps.

Usage:
  sidecars.py snapshot <source-dir> <snapshot.json>
  sidecars.py apply    <snapshot.json> <library.db> <clean-root> [quarantine-dir] [--apply]   # dry-run unless --apply
  sidecars.py prune-shells <source-dir> <quarantine-dir> [--apply]   # imported shells (no audio left) -> quarantine
"""
import sys, os, json, subprocess, shutil, sqlite3, re, glob
from collections import defaultdict

AUDIO = {'.mp3', '.flac', '.m4a', '.m4b', '.aac', '.alac', '.ogg', '.oga', '.opus', '.wma',
         '.wav', '.aif', '.aiff', '.ape', '.wv', '.mpc', '.tta', '.dsf', '.dff', '.mp2'}
ART = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.pdf'}
# official sidecar basenames only (case-insensitive, optional trailing number): cover, booklet, back, cd2...
OFFICIAL = re.compile(r'^(cover|front|folder|back|booklet|inlay|inside|sleeve|scan|scans|artwork|art|obi'
                      r'|matrix|label|digipak|digipack|cd|disc|disk)([ _.\-]?\d+)?$', re.I)
TOL = 6   # seconds: per-track tolerance (ffprobe vs beets/mutagen durations differ by a few seconds)
COVER = re.compile(r'^(cover|front|folder|artwork|art|sleeve|label)([ _.\-]?\d+)?$', re.I)  # "the cover" names


def is_sidecar(fn):
    base, ext = os.path.splitext(fn)
    ext = ext.lower()
    if ext == '.lrc':                       # lyrics: any name
        return True
    return ext in ART and bool(OFFICIAL.match(base))


def dur(path):
    try:
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                              '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip()
        return int(round(float(out))) if out else 0
    except Exception:
        return 0


def durs_of(paths):
    return sorted(d for d in (dur(p) for p in paths) if d > 0)


def matches(a, b):                          # both sorted; same count + each pair within TOL
    return len(a) == len(b) and all(abs(x - y) <= TOL for x, y in zip(a, b))


def snapshot(src, out):
    audio, side = defaultdict(list), defaultdict(list)
    for dp, _, files in os.walk(src):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in AUDIO:
                audio[dp].append(os.path.join(dp, fn))
            elif is_sidecar(fn):
                side[dp].append(os.path.join(dp, fn))
    snap = []
    for d, files in side.items():
        if not audio.get(d):
            continue
        ds = durs_of(audio[d])
        if ds:
            snap.append({"durs": ds, "files": sorted(files)})
    json.dump(snap, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"sidecars: snapshot {len(snap)} album(s) with official sidecars", file=sys.stderr)


def apply(snapfile, db, clean_root, dump, do_apply):
    snap = json.load(open(snapfile, encoding="utf-8"))
    if not snap:
        print("sidecars: nothing to carry", file=sys.stderr)
        return
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = defaultdict(list)
    for (path, length) in con.execute("SELECT path, length FROM items"):
        p = path.decode('utf-8', 'surrogateescape') if isinstance(path, bytes) else path
        if not os.path.isabs(p):                       # beets >=2.10 stores paths relative to the lib root
            p = os.path.join(clean_root, p)
        dst[os.path.dirname(p)].append(int(round(length or 0)))
    moved = dumped = miss = ambig = 0
    for ddir, lengths in dst.items():
        dd = sorted(x for x in lengths if x > 0)
        cands = [e for e in snap if matches(e["durs"], dd)]
        if len(cands) != 1:
            ambig += len(cands) > 1
            miss += len(cands) == 0
            continue
        has_cover = bool(glob.glob(os.path.join(ddir, "cover.*")))
        for f in cands[0]["files"]:
            if not os.path.exists(f):
                continue
            base, ext = os.path.splitext(os.path.basename(f))
            dest = os.path.join(ddir, os.path.basename(f))
            redundant = ext.lower() in ART and bool(COVER.match(base)) and has_cover   # cover already in clean
            if not redundant and not os.path.exists(dest):     # free slot -> MOVE into the album
                if do_apply:
                    shutil.move(f, dest)
                moved += 1
                print(f"{'MOVE' if do_apply else 'DRY '} {os.path.basename(f)} -> {ddir}")
            elif dump:                                         # dup / redundant cover -> quarantine/<source-folder>/ (never delete)
                qd = os.path.join(dump, os.path.basename(os.path.dirname(f)))
                qdest = os.path.join(qd, os.path.basename(f))
                if do_apply:
                    os.makedirs(qd, exist_ok=True)
                    shutil.move(f, qdest)
                dumped += 1
                print(f"{'DUMP' if do_apply else 'DRY '} {os.path.basename(f)} -> {qd}/")
    print(f"sidecars: {'moved' if do_apply else 'would move'} {moved} file(s), {dumped} dup(s) -> quarantine; "
          f"{miss} clean album(s) unmatched, {ambig} ambiguous", file=sys.stderr)


def prune_shells(src, dump, do_apply):
    """Imported-album shells (leaf source dirs with files but NO audio left) -> quarantine, whole folder."""
    targets = [dp for dp, dirs, files in os.walk(src)
               if dp != src and not dirs and files
               and not any(os.path.splitext(f)[1].lower() in AUDIO for f in files)]
    moved = 0
    for dp in targets:
        if not os.path.isdir(dp):
            continue
        dest = os.path.join(dump, os.path.basename(dp))
        i = 1
        while os.path.exists(dest):
            i += 1
            dest = os.path.join(dump, f"{os.path.basename(dp)} ({i})")
        if do_apply:
            os.makedirs(dump, exist_ok=True)
            shutil.move(dp, dest)
        moved += 1
        print(f"{'SHELL' if do_apply else 'DRY '} {os.path.basename(dp)}/ -> {dump}")
    print(f"sidecars: {moved} imported shell(s) -> quarantine", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "snapshot":
        snapshot(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "apply" and len([a for a in sys.argv[2:] if a != "--apply"]) >= 3:
        a = [x for x in sys.argv[2:] if x != "--apply"]
        apply(a[0], a[1], a[2], a[3] if len(a) > 3 else "", "--apply" in sys.argv)
    elif sys.argv[1] == "prune-shells" and len([a for a in sys.argv[2:] if a != "--apply"]) >= 2:
        a = [x for x in sys.argv[2:] if x != "--apply"]
        prune_shells(a[0], a[1], "--apply" in sys.argv)
    else:
        print(__doc__)
        sys.exit(1)

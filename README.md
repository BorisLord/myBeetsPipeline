# music-recovery

Recover, organize and enrich a chaotic music library (tens of thousands of loose, badly-tagged
files) into a clean **album** library you can serve with any player (e.g. Navidrome, Jellyfin, Plex).

Built on **beets** (latest). Files are re-matched by **AcoustID audio fingerprint** + tags,
so it is robust to duplicate track numbers, download-batch folders and untitled/failed rips — the
source folder structure is ignored.

**Strategy:** import in **album mode** with `move` — only **complete, strongly-matched albums** are
moved to the clean lib; everything not matched (singletons, weak/failed rips) stays in the source =
the leftover pile to curate later (e.g. Picard). Empty shells of moved albums are pruned after import.

---

## Quick start

```bash
git clone <repo-url> && cd music-recovery
./setup.sh     # installs beets (uv/pipx); if a system tool is missing it prints the command + stops -> re-run once
./run.sh       # full pipeline: import -> enrich -> replaygain -> QA
```

No config needed: by default everything lives under `~/Music/beetsPipeline/` (`source/`, `clean/`,
`quarantine/`). Put the music to import in `source/` — matched albums **move** to `clean/`, the rest stay
in `source/` to curate. Want other paths? Edit `config.env` (created by setup) and re-run `./setup.sh`.
For ongoing additions, drop albums in `source/` and let `scripts/process-inbox.sh` auto-import them (see below).

---

## Configuration

`setup.sh` already does all of this — this section is reference for **customizing**. Setup creates
`config.env` (gitignored) from `config.env.example` and deploys `beets/*.yaml` into `$BEETSDIR`, patching
`directory:` and `import.log:`. To change paths, edit `config.env` and re-run `./setup.sh`:

| Var | Meaning |
|---|---|
| `BEET` | beets binary (absolute path) |
| `BEETSDIR` | beets config dir (holds `config.yaml` + overlays) |
| `MUSIC_SRC` | messy source library to import **from** |
| `MUSIC_CLEAN` | clean album destination (point your player here) |
| `MUSIC_DUMP` | quarantine dir — cull here, **never `rm`** |

The one thing setup can't fill in: your **API keys** — set `fanarttv_key` / `lastfm_key` in
`$BEETSDIR/config.yaml` for online artwork + genres (optional; left as `REPLACE_ME` otherwise). Never commit keys.

---

## Requirements

`./setup.sh` installs **beets** for you (it asks: `uv`, `pipx`, or `mise`); for the system tools it
detects what's missing and prints the exact install command for your OS (apt/dnf/brew):

- **uv** / `pipx` / `mise` — to install beets (setup asks which); `helpers/` run via `uv run --with mediafile --with mutagen python …`.
- **beets** (latest). MusicBrainz is now a separate plugin → `plugins:` MUST include `musicbrainz`,
  otherwise `chroma` yields no MusicBrainz candidates and matching finds nothing.
- **fpcalc / Chromaprint** — for the `chroma` (AcoustID) fingerprint matching.
- **ffmpeg** — for the ReplayGain step.
- **flac + mp3val** — for the `04-qa` file-integrity check (`beet bad`); `mp3val` is best-effort (not in every distro).

---

## Pipeline

Each script sources `config.env` and backs up `library.db` before running.

| Step | Script | Role |
|---|---|---|
| **1 — match** | `scripts/01-import.sh` | Album import with **AcoustID + tags**. Only complete, strong albums are kept (`quiet`, weak matches → skip). Scrub + folder cover during import; official sidecars (booklet/back/scan/`.lrc`) moved into clean. |
| **2 — enrich** | `scripts/02-enrich.sh` | `lastgenre` (genres), `ftintitle` (move "feat. X" out of the artist field into the title), front artwork. |
| **3 — replaygain** | `scripts/03-replaygain.sh` | ReplayGain (EBU R128 volume, ffmpeg backend) — overlay `beets/replaygain.yaml`. |
| **4 — QA** | `scripts/04-qa.sh` | Technical audit: format/bitrate/WMA, duplicates, integrity (`beet bad` for mp3/flac + ffmpeg decode for every other format), **junk metadata** cleanup (URLs/EAC/LAME in comments + encoder via `zero`) — overlay `beets/qa.yaml`. |

**On-demand tools** (not numbered steps):
- `scripts/anomaly-scan.py` — READ-ONLY scan → one TSV per anomaly family (junk album names, artist/album spelling variants, `feat.` in albumartist, disc-number-in-name, dups, orphans) for manual review.
- `scripts/sidecars.py` — snapshot/apply tool that step 1 uses to **move** official sidecars (booklet/back/scan/`.lrc`) from source into the matched clean album (matched by audio duration; a copy already in clean → quarantine, never deleted).

`helpers/` fix the scrub crash on embedded images with `mime=None` (WMA/ASF). Run them via uv (it
pulls the needed libs): `uv run --with mediafile --with mutagen python helpers/<x>.py` —
`scan-scrub-crash.py` to find them, then `mutagen-strip.py` / `strip-broken-art.py` (`ROOT=`/`EXTS=`).

Path templates (`config.yaml`): `$albumartist/$album/…`, compilations under `Various Artists/…`,
VA soundtracks under `Soundtracks/…`. The `beets/fetchart-fs.yaml` overlay prefers the folder cover.

**Logs:** all logs live in `$LOG_DIR` (default `~/Music/beetsPipeline/logs/`, next to your library;
override in `config.env`). One file per pass, always **appended** (never overwritten): `01-import.log`,
`02-enrich.log`, `03-replaygain.log`, `04-qa.log`, `inbox.log` (cron), plus `import-decisions.log`
(beets' match/skip decisions).

---

## How matching works

beets identifies albums by **content, not by file/folder names** — so it copes with mis-tagged and
mis-named files. Per source folder:

1. **Group** — audio files in a folder = one album candidate (hidden + video files are ignored).
2. **Fingerprint + tags** — each candidate gets an **AcoustID** fingerprint (`chroma`/`fpcalc`) and its
   tags are read, then matched against **MusicBrainz** releases.
3. **Score** — a distance is computed (`strong_rec_thresh: 0.10` = strong); missing/extra tracks are
   penalized (`max_rec`), so only **complete** albums pass strongly.
4. **Decide** — `quiet` + `quiet_fallback: skip`: strong matches auto-accept, everything else is
   **skipped** (it never guesses).
5. **Act** — accepted → files **move** to `MUSIC_CLEAN`, reorganized by the path templates, scrubbed,
   with the folder cover + official sidecars (booklet/back/scan/`.lrc`) **moved** over (a dup already in
   clean → quarantine, never deleted). Unmatched files **stay** in the source = your curation pile; empty shells pruned.

**Formats:** all common types work — MP3, FLAC, M4A/AAC/ALAC, Ogg/Opus, WMA, APE, WavPack, AIFF… (tags
via mediafile/mutagen, audio via ffmpeg/fpcalc). WAV carries almost no tags by design, and WMA/ASF with a
broken embedded image needs the `helpers/` pre-strip first (see Lessons).

Drop complete **album folders** (not loose files); `incremental: yes` records done folders, so
re-running only processes new drops.

---

## Auto-import (drop & go)

**When does it run?** Out of the box, nothing watches the folder — you run `./run.sh` yourself. The
optional auto-import uses **cron** (the simplest, most portable, battle-tested choice); `setup.sh` offers
to add the entry, or add it yourself (fix the path):

`*/15 * * * * PATH=$HOME/.local/bin:$HOME/.local/share/mise/shims:/usr/bin:/bin /bin/bash /path/to/scripts/process-inbox.sh >> /path/to/import.log 2>&1`

Each run, `scripts/process-inbox.sh` checks the source: if a folder was dropped it **waits until the
copy/download has finished** (debounce on folder size — a half-copied folder is never imported), takes a
lock (no concurrent run), imports it (strong → `clean/`, weak/untagged → left in `source/`), then enriches
the day's additions (genres + ftintitle + artwork + replaygain). Empty and already-done folders are
skipped, so polling is cheap — and ≤15 min latency is irrelevant for music imports (why cron beats a
real-time watcher here).

**Interventions:** a well-tagged, complete album → auto-imported, nothing to do. Whatever is *not*
auto-matched (weak/untagged/incomplete) stays in `$MUSIC_SRC` → review it (fix tags in Picard so it
re-imports, or move it to `$MUSIC_DUMP`). Occasionally run `04-qa.sh` + `anomaly-scan.py` for QA.

---

## Uninstall

`./uninstall.sh` removes the **tooling only** — the cron auto-import entry, the beets config dir
(`$BEETSDIR`, incl. the `library.db` catalog), `config.env` + `import.log`, and optionally beets itself
(prompted). It **never touches your music**: `MUSIC_SRC`, `MUSIC_CLEAN` and `MUSIC_DUMP` are left exactly
as they are — delete those by hand if you really want them gone.

---

## Lessons / gotchas (verified in production)

- **Scrub crashes on `mime=None` images** (WMA/ASF): strip the image first with `helpers/` (run via
  `uv run --with mediafile --with mutagen python …`). **Never disable scrub** — it runs on every move.
- **Quarantine, don't `rm`.** Cull by moving to `$MUSIC_DUMP`; an accidental delete once destroyed
  thousands of tracks. If your filesystem supports snapshots (ZFS/btrfs/LVM), snapshot before any mass
  op, and `cp library.db` first. Only empty dir shells may be `rmdir`'d.
- **Never dedup on the db alone.** The same recording can legitimately be on a studio album AND a
  compilation. Correlate the files (duration + bitrate), keep the best bitrate, never break an album.
- **Compilations group by album TITLE, not albumartist** (else VA comps scatter one group per
  artist); then exclude generic titles + dominant-artist albums.
- **Back up `library.db`** before any bulk `modify`/`move`/`remove` (the scripts do it automatically).
- **Never use `--from-logfile`** on these logs (parent paths + names with `;` → recursion). Import
  the directory directly.
- **WMA format is stored as "Windows Media"** → query `format::Windows`, not `format:WMA`.
- **Rate-limiting is NOT the cause of skips** (0 real 429/503 over 10k+ evaluations); skips = weak
  match + quiet mode refusing to guess. No personal AcoustID key needed (non-commercial use is free).

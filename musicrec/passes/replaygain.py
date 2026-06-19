"""Pass 3 -- ReplayGain (EBU R128 / ITU-R BS.1770 via ffmpeg backend), track + album.
Uses the replaygain.yaml overlay (overwrite: yes). Writes RG tags; the player applies normalization.
"""
import shutil

from ..beets import run_beet
from ..logs import get_logger
from ..util import backup_db


def run(cfg, query: str = "") -> int:
    log = get_logger("replaygain")
    if not shutil.which("ffmpeg"):
        log.error("ffmpeg required (replaygain backend) -- install ffmpeg")
        return 1
    backup_db(cfg, "bak", log)
    q = [query] if query else []
    rc, _ = run_beet(cfg, ["replaygain", *q], overlay="replaygain.yaml", passname="replaygain")
    if rc:
        log.error("replaygain failed (rc=%d)", rc)
    return rc

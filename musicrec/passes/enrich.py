"""Pass 2 -- enrichment: front art + genres + 'feat.' normalization. Independently retryable.
(front cover only; booklet/back/scans/.lrc are carried by the import pass via sidecars.)
"""
from ..beets import run_beet
from ..logs import get_logger
from ..util import backup_db


def run(cfg, query: str = "") -> int:
    log = get_logger("enrich")
    backup_db(cfg, "bak", log)
    q = [query] if query else []
    rc = 0
    # run all four (one failing step shouldn't block the others), but report failure if any errored
    for args in (["fetchart", *q], ["embedart", "-y", *q], ["lastgenre", *q], ["ftintitle", *q]):
        step_rc, _ = run_beet(cfg, args, passname="enrich")
        if step_rc:
            log.error("step failed (rc=%d): beet %s", step_rc, " ".join(str(a) for a in args))
            rc = step_rc
    return rc

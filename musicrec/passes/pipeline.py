"""The ONE pipeline: import -> enrich -> replaygain -> qa. `run` (manual) and `inbox` (cron) both call
this; only the trigger differs. Incremental by default (watermark = last successful run): enrich/rg/qa are
scoped to items added since then -- "omit what the previous run already did". `full=True` reprocesses all.

Fail-fast: a writing pass (import/enrich/replaygain) that errors does NOT get swallowed -- the watermark is
NOT advanced and the run reports failure, so the next run retries instead of skipping broken work. QA is a
read-only audit, so its result is informational and never gates the watermark.
"""
from datetime import datetime

from .. import state
from ..logs import get_logger
from . import enrich, import_, qa, replaygain


def run(cfg, *, full: bool = False, src=None) -> int:
    log = get_logger("pipeline")
    wm_old = None if full else state.get_watermark(cfg)
    scope = state.added_query(wm_old)        # "" in full mode / first run -> whole library
    log.info("pipeline start (%s)%s", "full" if full else "incremental", f" scope={scope}" if scope else "")

    rc = import_.run(cfg, src=src)
    if rc:
        log.error("pipeline ABORTED: import failed (rc=%d) -- watermark NOT advanced, nothing re-skipped", rc)
        return rc
    # capture the new watermark AFTER import: this run's freshly-added items are < wm_new, so the NEXT run's
    # `added:<wm_new>..` excludes them; this run still covers them via the OLD watermark in `scope`.
    wm_new = datetime.now().replace(microsecond=0).isoformat()

    rc_enrich = enrich.run(cfg, query=scope)
    rc_rg = replaygain.run(cfg, query=scope)
    qa.run(cfg, scope=scope)                 # read-only audit: informational, does not gate the watermark

    if rc_enrich or rc_rg:
        log.error("pipeline FAILED (enrich rc=%d, replaygain rc=%d) -- watermark NOT advanced; "
                  "fix the cause and re-run (the next run will retry these items)", rc_enrich, rc_rg)
        return rc_enrich or rc_rg

    state.set_watermark(cfg, wm_new)
    log.info("pipeline done; watermark -> %s", wm_new)
    return 0

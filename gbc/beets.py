"""Drive beets via subprocess -- the documented, canonical interface.

The robustness fix vs the old bash glue: beets writes much of its output (incl. the `--pretend` plan)
to STDERR, not stdout. Here we MERGE stdout+stderr, log every line (tagged by pass), AND return the full
text so callers can parse it (e.g. detect the import plan). BEETSDIR is always set in the child env, so
there is no "variable not propagated" class of bug.
"""
import os
import subprocess

from .config import Config
from .logs import get_logger


def run_beet(cfg: Config, args, *, overlay: str | None = None, passname: str,
             echo_lines: bool = True) -> tuple[int, str]:
    """Run `beet [-c overlay] <args...>`. Returns (returncode, merged_output_text).

    echo_lines=True logs every output line (the run narrative: match decisions, fetchart, replaygain).
    echo_lines=False captures silently -- for `ls`/counts/queries we parse rather than dump to the log.
    """
    log = get_logger(passname)
    cmd = [cfg.beet]
    if overlay:
        cmd += ["-c", str(cfg.overlay(overlay))]
    cmd += [str(a) for a in args]
    env = dict(os.environ, BEETSDIR=str(cfg.beetsdir))
    log.info("$ %s", " ".join(cmd))
    lines: list[str] = []
    try:
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, bufsize=1, env=env) as proc:
            assert proc.stdout is not None     # PIPE is always set above
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                lines.append(line)
                if echo_lines and line.strip():
                    log.info("%s", line)
    except FileNotFoundError as e:
        raise RuntimeError(f"beet not found ({cfg.beet!r}) -- install beets or run ./setup.sh") from e
    return proc.returncode, "\n".join(lines)

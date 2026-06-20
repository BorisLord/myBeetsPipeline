"""Read beets' RESOLVED import config and derive how gbc must adapt -- gbc respects beets on every point:
the import OPERATION (move / copy / link / hardlink / reflink / delete) is beets' decision, not gbc's.

`beet config` prints the fully merged config (beets defaults + config.yaml + overlays) as YAML, so this is
the EFFECTIVE behaviour, never a guess from the file. From it we derive two booleans the passes branch on:
  source_consumed   -- beets removes the originals (move, or delete after copy/link) -> gbc MAY move source.
  clean_independent -- clean holds a real standalone copy (copy / reflink / hardlink, NOT symlink/in-place)
                       -> reclaiming a verified source original is safe.
When the source is PRESERVED, gbc keeps it READ-ONLY (no dedup / sidecars / prune); the reclaim pass
(post-verify) is the only thing allowed to move a source original, and only when clean_independent.
"""
import io
from dataclasses import dataclass

import yaml

from .beets import run_beet
from .config import Config
from .logs import get_logger

REQUIRED_PLUGINS = ("musicbrainz", "chroma", "scrub")  # match candidates / tag hygiene gbc depends on


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("yes", "true", "on", "1")


@dataclass(frozen=True)
class BeetsImport:
    move: bool = False
    copy: bool = False
    link: bool = False
    hardlink: bool = False
    reflink: bool = False
    delete: bool = False

    @property
    def source_consumed(self) -> bool:
        """beets itself removes the source originals (move, or copy/link followed by delete)."""
        return self.move or self.delete

    @property
    def source_preserved(self) -> bool:
        return not self.source_consumed

    @property
    def makes_copy(self) -> bool:
        """A real standalone file lands in clean (vs an in-place add, or a symlink back to the source)."""
        return self.copy or self.reflink or self.hardlink

    @property
    def clean_independent(self) -> bool:
        """Safe to reclaim a verified source original: clean keeps a standalone copy AND source is preserved."""
        return self.source_preserved and self.makes_copy

    @property
    def label(self) -> str:
        for name in ("move", "delete", "reflink", "hardlink", "link", "copy"):
            if getattr(self, name):
                return name
        return "in-place"


def parse_import(config_text: str) -> BeetsImport:
    """Build BeetsImport from `beet config` YAML text (pure -> unit-testable without a beets install)."""
    try:
        data = yaml.safe_load(io.StringIO(config_text)) or {}
    except yaml.YAMLError:
        data = {}
    imp = data.get("import", {}) if isinstance(data, dict) else {}
    if not isinstance(imp, dict):
        imp = {}
    return BeetsImport(
        move=_as_bool(imp.get("move", False)),
        copy=_as_bool(imp.get("copy", False)),
        link=_as_bool(imp.get("link", False)),
        hardlink=_as_bool(imp.get("hardlink", False)),
        reflink=_as_bool(imp.get("reflink", False)),
        delete=_as_bool(imp.get("delete", False)),
    )


def _warn_missing_plugins(config_text: str, log) -> None:
    try:
        data = yaml.safe_load(io.StringIO(config_text)) or {}
    except yaml.YAMLError:
        return
    plugins = data.get("plugins", "") if isinstance(data, dict) else ""
    if isinstance(plugins, list):
        plugins = " ".join(str(p) for p in plugins)
    enabled = str(plugins).split()
    missing = [p for p in REQUIRED_PLUGINS if p not in enabled]
    if missing:
        log.warning("beets plugins missing %s -> match/scrub silently underperform (AGENTS.md rule 7)", missing)


def read_import(cfg: Config) -> BeetsImport:
    """`beet config` (resolved) -> the effective import op; warns if a plugin gbc depends on is absent."""
    log = get_logger("beetscfg")
    _, text = run_beet(cfg, ["config"], passname="beetscfg", echo_lines=False)
    _warn_missing_plugins(text, log)
    bi = parse_import(text)
    log.info("beets import op = %s (source %s, clean %s)", bi.label,
             "preserved" if bi.source_preserved else "consumed",
             "independent" if bi.clean_independent else "linked/in-place")
    return bi

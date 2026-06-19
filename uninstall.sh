#!/bin/bash
# Uninstall the pipeline TOOLING: cron auto-import entry, beets config dir (incl. the library.db catalog),
# config.env + import.log, and optionally beets itself.
# It NEVER touches your music -- MUSIC_SRC / MUSIC_CLEAN / MUSIC_DUMP are left exactly as they are.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/config.env" ] && . "$HERE/config.env"
: "${BEETSDIR:=$HOME/.config/beets-rebuild}"
: "${LOG_DIR:=$(dirname "${MUSIC_CLEAN:-$HOME/Music/beetsPipeline/clean}")/logs}"
if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; D=$'\e[2m'; R=$'\e[0m'; else B=; G=; D=; R=; fi

echo "${B}music-recovery uninstall${R} ${D}-- removes tooling only; your music is never touched${R}"
echo

# 1. cron auto-import entry
if command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -qF "scripts/process-inbox.sh"; then
  crontab -l 2>/dev/null | grep -vF "scripts/process-inbox.sh" | crontab -
  echo "  [x] removed cron auto-import entry"
else
  echo "  [-] no cron entry"
fi

# 2. beets config dir (config.yaml + overlays + library.db catalog + logs/backups) -- guarded + confirmed
if [ -d "$BEETSDIR" ] && [ "$BEETSDIR" != "$HOME" ] && [ "$BEETSDIR" != "/" ]; then
  read -rp "  remove beets config dir + catalog ($BEETSDIR)? [y/N] " a
  if [ "$a" = y ] || [ "$a" = Y ]; then rm -rf "$BEETSDIR"; echo "  [x] removed $BEETSDIR"; else echo "  [-] kept $BEETSDIR"; fi
else
  echo "  [-] no beets config dir"
fi

# 3. logs + local config.env
if [ -d "$LOG_DIR" ]; then rm -rf "$LOG_DIR"; echo "  [x] removed logs ($LOG_DIR)"; fi
rm -f "$HERE/config.env" 2>/dev/null && echo "  [x] removed config.env"

# 4. beets itself (optional)
if command -v beet >/dev/null 2>&1; then
  read -rp "  uninstall beets itself too? [y/N] " a
  if [ "$a" = y ] || [ "$a" = Y ]; then
    if uv tool uninstall beets 2>/dev/null || pipx uninstall beets 2>/dev/null || mise unuse -g "pipx:beets" 2>/dev/null; then
      echo "  [x] beets uninstalled"
    else
      echo "  [!] couldn't auto-uninstall beets -- remove it manually"
    fi
  else
    echo "  [-] kept beets"
  fi
fi

echo
echo "${G}done.${R} ${B}Your music is untouched:${R}"
echo "    source      ${MUSIC_SRC:-(was not set)}"
echo "    clean       ${MUSIC_CLEAN:-(was not set)}"
echo "    quarantine  ${MUSIC_DUMP:-(was not set)}"
echo "  ${D}delete those by hand if you really want to -- this script never will${R}"

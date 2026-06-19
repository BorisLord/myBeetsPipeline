#!/bin/bash
# Remove the tooling (never your music). Delegates to `gbc uninstall`, then optionally removes the
# gbc + beets CLIs. MUSIC_SRC / MUSIC_CLEAN / MUSIC_DUMP are never touched.
set -uo pipefail
if command -v gbc >/dev/null 2>&1; then
  gbc uninstall "$@"          # cron entry, logs, config.env (+ --purge: beets config dir + catalog)
else
  echo "gbc not installed -- nothing to remove (your music is untouched)."
fi
read -rp "uninstall the gbc CLI itself (uv tool)? [y/N] " a
if [ "$a" = y ] || [ "$a" = Y ]; then uv tool uninstall gbc 2>/dev/null && echo "  removed gbc CLI"; fi
read -rp "uninstall beets too? [y/N] " a
if [ "$a" = y ] || [ "$a" = Y ]; then uv tool uninstall beets 2>/dev/null && echo "  removed beets"; fi
echo "done. Your music (source / clean / quarantine) is untouched."

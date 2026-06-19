#!/bin/bash
# Remove the tooling (never your music). Delegates to `musicrec uninstall`, then optionally removes the
# musicrec + beets CLIs. MUSIC_SRC / MUSIC_CLEAN / MUSIC_DUMP are never touched.
set -uo pipefail
if command -v musicrec >/dev/null 2>&1; then
  musicrec uninstall "$@"          # cron entry, logs, config.env (+ --purge: beets config dir + catalog)
else
  echo "musicrec not installed -- nothing to remove (your music is untouched)."
fi
read -rp "uninstall the musicrec CLI itself (uv tool)? [y/N] " a
if [ "$a" = y ] || [ "$a" = Y ]; then uv tool uninstall musicrec 2>/dev/null && echo "  removed musicrec CLI"; fi
read -rp "uninstall beets too? [y/N] " a
if [ "$a" = y ] || [ "$a" = Y ]; then uv tool uninstall beets 2>/dev/null && echo "  removed beets"; fi
echo "done. Your music (source / clean / quarantine) is untouched."

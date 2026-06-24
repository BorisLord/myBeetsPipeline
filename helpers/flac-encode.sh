#!/bin/sh
# WAV/AIFF/ALAC -> FLAC (lossless), called by the beets `convert` plugin (convert.yaml `flac` format).
# Validates the FLAC actually decodes BEFORE returning 0: beets' keep_new moves the lossless original to
# quarantine only when this command SUCCEEDS, so a non-zero exit here keeps the original safely in place
# (never lose the only good copy to a silently-broken encode -- ffmpeg can exit 0 on a truncated output).
# Args: $1=source $2=dest.
src="$1"
dst="$2"
# -map_metadata -1: drop ALL source container tags (junk like major_brand, foreign frames) -- beets re-writes
# its own clean tags + re-embeds art afterward (keep_new). -vn drops any source cover stream (re-embedded too).
ffmpeg -v error -i "$src" -y -vn -map_metadata -1 -acodec flac "$dst" || exit 1
if [ ! -s "$dst" ] || ! ffmpeg -v error -xerror -i "$dst" -f null - >/dev/null 2>&1; then
    rm -f "$dst"
    exit 1
fi

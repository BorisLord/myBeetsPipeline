#!/bin/bash
# Guided one-time setup: check/install beets, check system tools, create config.env, deploy the config.
# Run:  ./setup.sh   (re-run after installing anything it flags as missing).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# styling -- only when writing to a real terminal (plain text when piped/redirected)
if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; D=$'\e[2m'; R=$'\e[0m'
else B=; G=; Y=; C=; D=; R=; fi
step() { echo; echo "${B}${C}=== $1 ===${R}"; }
have() { command -v "$1" >/dev/null 2>&1; }

step "STEP 1/4  Dependencies"
have beet   && echo "  ${G}[ok]${R} beets   $(beet --version 2>/dev/null | head -1)" || echo "  ${Y}[--]${R} beets   ${Y}MISSING${R}"
have fpcalc && echo "  ${G}[ok]${R} fpcalc  ${D}chromaprint / AcoustID matching${R}" || echo "  ${Y}[--]${R} fpcalc  ${Y}MISSING${R} ${D}(chromaprint / AcoustID matching)${R}"
have ffmpeg && echo "  ${G}[ok]${R} ffmpeg  ${D}replaygain${R}"                      || echo "  ${Y}[--]${R} ffmpeg  ${Y}MISSING${R} ${D}(replaygain)${R}"
have flac   && echo "  ${G}[ok]${R} flac    ${D}04-qa integrity${R}"                 || echo "  ${Y}[--]${R} flac    ${Y}MISSING${R} ${D}(04-qa integrity)${R}"
have mp3val && echo "  ${G}[ok]${R} mp3val  ${D}optional${R}"                         || echo "  ${D}[~~] mp3val  optional, not installed${R}"
echo "  ${D}installers: uv=$(have uv && echo yes || echo no)  pipx=$(have pipx && echo yes || echo no)  mise=$(have mise && echo yes || echo no)${R}"

# beets: ASK how to install (uv recommended, then pipx or mise); user-space, no sudo.
# [chroma,fetchart,lastgenre] extras pull pyacoustid + requests + Pillow + pylast (verified beets extras).
if ! have beet; then
  echo
  if have uv || have pipx || have mise; then
    PKG='beets[chroma,fetchart,lastgenre]'
    echo "  beets is missing -- install it with:"
    have uv   && echo "    u) uv tool   (recommended)"
    have pipx && echo "    p) pipx"
    have mise && echo "    m) mise      (pipx backend)"
    echo "    s) skip (install it yourself, then re-run)"
    c=s; [ -t 0 ] && read -rp "  choice: " c
    case "$c" in
      [uU]) if have uv;   then uv tool install "$PKG" && { uv tool update-shell >/dev/null 2>&1 || true; }; else echo "  uv not installed"; fi ;;
      [pP]) if have pipx; then pipx install "$PKG" && pipx ensurepath >/dev/null; else echo "  pipx not installed"; fi ;;
      [mM]) if have mise; then mise use -g "pipx:$PKG"; else echo "  mise not installed"; fi ;;
      *) echo "  skipped beets" ;;
    esac
    export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"
  else
    echo "  beets is missing and no installer (uv/pipx/mise) found -- install one first:"
    echo "    uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "    pipx            : python3 -m pip install --user pipx"
  fi
fi

# system tools: report the exact install command (no hidden sudo)
need=()
have fpcalc || need+=(fpcalc)
have ffmpeg || need+=(ffmpeg)
have flac   || need+=(flac)
if [ ${#need[@]} -gt 0 ]; then
  echo
  echo "  ${Y}install the missing system tools (${need[*]}) with your package manager:${R}"
  echo "    Debian/Ubuntu : sudo apt install -y libchromaprint-tools ffmpeg flac mp3val"
  echo "    Fedora        : sudo dnf install -y chromaprint-tools ffmpeg flac mp3val"
  echo "    macOS (brew)  : brew install chromaprint ffmpeg flac"
fi

# gate: stop until everything required is present
if ! have beet || [ ${#need[@]} -gt 0 ]; then
  echo
  echo "  ${Y}>> install the items above, then re-run ./setup.sh${R}"
  exit 1
fi
echo "  ${G}-> all dependencies present${R}"

step "STEP 2/4  Config (config.env)"
if [ ! -f "$HERE/config.env" ]; then
  cp "$HERE/config.env.example" "$HERE/config.env"
  echo "  created config.env ${D}(defaults under ~/Music/beetsPipeline/ -- edit + re-run for other paths)${R}"
else
  echo "  using existing config.env"
fi
. "$HERE/config.env"
: "${LOG_DIR:=$(dirname "$MUSIC_CLEAN")/logs}"
echo "    source      $MUSIC_SRC"
echo "    clean       $MUSIC_CLEAN"
echo "    quarantine  ${MUSIC_DUMP:-$HOME/Music/beetsPipeline/quarantine}"
echo "    logs        $LOG_DIR"
echo "    beetsdir    $BEETSDIR"

step "STEP 3/4  Deploy beets config"
mkdir -p "$BEETSDIR" "$MUSIC_SRC" "$MUSIC_CLEAN" "${MUSIC_DUMP:-$HOME/Music/beetsPipeline/quarantine}" "$LOG_DIR"
cp "$HERE"/beets/*.yaml "$BEETSDIR/"
# portable in-place edit (GNU vs BSD/macOS `sed -i` differ) -> sed to a temp file, then move
tmp=$(mktemp "${TMPDIR:-/tmp}/beets-setup.XXXXXX")
sed -e "s#^directory:.*#directory: $MUSIC_CLEAN#" -e "s#^  log:.*#  log: $LOG_DIR/import-decisions.log#" \
    "$BEETSDIR/config.yaml" > "$tmp" && mv "$tmp" "$BEETSDIR/config.yaml"
echo "  deployed beets/*.yaml -> $BEETSDIR ${D}(directory + log auto-filled)${R}"
echo "  ${D}optional: add fanarttv_key / lastfm_key in $BEETSDIR/config.yaml for online art + genres${R}"

step "STEP 4/4  Auto-import on drop (optional)"
CRON_LINE="*/15 * * * * PATH=$HOME/.local/bin:$HOME/.local/share/mise/shims:/usr/local/bin:/usr/bin:/bin /bin/bash $HERE/scripts/process-inbox.sh >/dev/null 2>&1"
cron_on=no
if command -v crontab >/dev/null 2>&1 && [ -t 0 ]; then
  if crontab -l 2>/dev/null | grep -qF "scripts/process-inbox.sh"; then
    echo "  already scheduled ${D}(crontab -l)${R}"; cron_on=yes
  else
    read -rp "  Auto-import dropped folders every 15 min via cron? [y/N] " a
    if [ "$a" = y ] || [ "$a" = Y ]; then
      (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
      echo "  ${G}scheduled${R} ${D}(edit/remove with: crontab -e)${R}"; cron_on=yes
    else
      echo "  skipped ${D}(run ./run.sh yourself; see README Auto-import)${R}"
    fi
  fi
else
  echo "  ${D}(no crontab / non-interactive) -- run ./run.sh, or add the cron line manually (README)${R}"
fi

echo
echo "${B}${G}========================================${R}"
echo "${B}${G} SETUP COMPLETE${R}"
echo "   put album folders in:  ${B}$MUSIC_SRC${R}"
if [ "$cron_on" = yes ]; then
  echo "   ${D}->${R} auto-imported within ~15 min (cron) -- or run now: ${B}./run.sh${R}"
else
  echo "   ${D}->${R} then run the pipeline: ${B}./run.sh${R}"
fi
echo "${B}${G}========================================${R}"

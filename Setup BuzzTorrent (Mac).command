#!/bin/bash
# =============================================================================
#  BuzzTorrent setup for macOS
#  Double-click (first time: right-click > Open > Open). Safe to run again:
#  anything already installed is skipped, and every step asks first.
#
#  Installs with Homebrew (https://brew.sh):
#    Python 3        runs BuzzTorrent
#    aria2           BuzzTorrent's built-in torrent downloader
#    ClamAV          virus scan of every finished download (+ its virus database)
#    Google Chrome   only if no Chrome/Edge/Brave: shows BuzzTorrent in its own app window
#    VLC             optional: plays every video format
#    Jackett         optional: more torrent sites (you choose which)
#  Then adds BuzzTorrent to your Applications folder and starts it.
# =============================================================================
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"

bold() { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "   \033[32m✓\033[0m %s\n" "$*"; }
note() { printf "   %s\n" "$*"; }
ask()  { local a; read -r -p "   $1 [Y/n] " a; [ "$a" != "n" ] && [ "$a" != "N" ]; }
askn() { local a; read -r -p "   $1 [y/N] " a; [ "$a" = "y" ] || [ "$a" = "Y" ]; }
finish() { echo; read -r -p "   Press Return to close this window. " _; exit "${1:-0}"; }

bold "BuzzTorrent setup for Mac"
note "Folder: $HERE"

# ---- macOS version ----------------------------------------------------------
major="$(sw_vers -productVersion | cut -d. -f1)"
if [ "${major:-0}" -lt 11 ]; then
  note "BuzzTorrent needs macOS 11 (Big Sur) or newer; this Mac has $(sw_vers -productVersion)."
  finish 1
fi
ok "macOS $(sw_vers -productVersion) on $(uname -m)"

# ---- Homebrew ---------------------------------------------------------------
bold "1/8  Homebrew (installs the free tools below)"
for d in /opt/homebrew/bin /usr/local/bin; do
  [ -x "$d/brew" ] && eval "$("$d/brew" shellenv)"
done
if command -v brew >/dev/null 2>&1; then
  ok "Homebrew $(brew --version | head -1 | cut -d' ' -f2)"
else
  note "Homebrew isn't installed. Its official installer asks for your Mac password."
  if ask "Install Homebrew now?"; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
      note "Homebrew didn't install. See https://brew.sh, then run this setup again."; finish 1; }
    for d in /opt/homebrew/bin /usr/local/bin; do
      [ -x "$d/brew" ] && eval "$("$d/brew" shellenv)"
    done
    # make brew available in new Terminal windows too (what Homebrew itself recommends)
    if ! grep -qs "brew shellenv" "$HOME/.zprofile"; then
      echo "eval \"\$($(command -v brew) shellenv)\"" >> "$HOME/.zprofile"
    fi
    ok "Homebrew installed"
  else
    note "Skipped. Without Homebrew, install Python 3.10+ from https://www.python.org/downloads/macos/"
  fi
fi
HAVE_BREW=0; command -v brew >/dev/null 2>&1 && HAVE_BREW=1

# ---- Python -----------------------------------------------------------------
bold "2/8  Python 3.10 or newer"
find_python() {
  for c in python3 python3.13 python3.12 python3.11 python3.10 \
           /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}
PY="$(find_python)"
if [ -z "$PY" ] && [ "$HAVE_BREW" = 1 ]; then
  if ask "Install Python with Homebrew?"; then brew install python; PY="$(find_python)"; fi
fi
if [ -z "$PY" ]; then
  note "Python 3.10+ is required. Install it (https://www.python.org/downloads/macos/) and run this setup again."
  open "https://www.python.org/downloads/macos/"
  finish 1
fi
ok "$("$PY" --version) at $PY"

# ---- aria2 ------------------------------------------------------------------
bold "3/8  aria2: the built-in torrent downloader"
if command -v aria2c >/dev/null 2>&1; then
  ok "aria2 $(aria2c --version | head -1 | awk '{print $3}')"
elif [ "$HAVE_BREW" = 1 ] && ask "Install aria2 (so BuzzTorrent downloads torrents itself)?"; then
  brew install aria2 && ok "aria2 installed"
else
  note "Skipped: BuzzTorrent will hand downloads to another torrent app instead."
fi

# ---- ClamAV -----------------------------------------------------------------
bold "4/8  ClamAV: virus scan of every download"
if ! command -v clamscan >/dev/null 2>&1 && [ "$HAVE_BREW" = 1 ]; then
  if ask "Install ClamAV (free antivirus, takes a few minutes)?"; then brew install clamav; fi
fi
if command -v clamscan >/dev/null 2>&1; then
  CONF="$(brew --prefix 2>/dev/null)/etc/clamav"
  if [ -d "$CONF" ] && [ ! -f "$CONF/freshclam.conf" ] && [ -f "$CONF/freshclam.conf.sample" ]; then
    sed 's/^Example/#Example/' "$CONF/freshclam.conf.sample" > "$CONF/freshclam.conf"
  fi
  note "Updating the virus database (first time: about 300 MB)…"
  if freshclam --quiet; then ok "ClamAV ready, virus database up to date"
  else note "The virus database update failed (check the internet connection); run this setup again or type 'freshclam' later."; fi
else
  note "No antivirus: BuzzTorrent still checks what's inside every download (fake videos, hidden programs)."
fi

# ---- VLC (optional) ---------------------------------------------------------
bold "5/8  VLC (optional): plays every video format"
if [ -d "/Applications/VLC.app" ] || [ -d "$HOME/Applications/VLC.app" ]; then
  ok "VLC"
elif [ "$HAVE_BREW" = 1 ] && askn "Install VLC (for MKV and other formats the app window can't play)?"; then
  brew install --cask vlc && ok "VLC installed"
else
  note "Skipped: videos the app window can't play open in QuickTime instead."
fi

# ---- App window browser -----------------------------------------------------
bold "6/8  A browser for BuzzTorrent's own window"
BROWSER=""
for app in "Google Chrome" "Microsoft Edge" "Brave Browser" "Chromium"; do
  for base in /Applications "$HOME/Applications"; do
    [ -z "$BROWSER" ] && [ -d "$base/$app.app" ] && BROWSER="$app"
  done
done
if [ -n "$BROWSER" ]; then
  ok "$BROWSER (BuzzTorrent opens in its own window, and quits when you close it)"
elif [ "$HAVE_BREW" = 1 ] && ask "Install Google Chrome, so BuzzTorrent gets its own app window?"; then
  brew install --cask google-chrome && ok "Google Chrome installed"
else
  note "Skipped: BuzzTorrent opens as a Safari tab instead (quit it with Stop BuzzTorrent.command)."
fi

# ---- Jackett (optional) -----------------------------------------------------
bold "7/8  Jackett (optional): more torrent sites"
note "Without it, BuzzTorrent searches the Internet Archive (free, legal films, music, books)."
note "With it, you choose torrent sites; what you download from them, and whether that's legal where you live, is up to you."
if [ "$HAVE_BREW" = 1 ] && askn "Install Jackett and connect it to BuzzTorrent?"; then
  brew install jackett && brew services start jackett
  note "Waiting for Jackett to start…"
  for _ in $(seq 1 30); do
    [ -f "$HOME/.config/Jackett/ServerConfig.json" ] && curl -s -o /dev/null http://127.0.0.1:9117 && break
    sleep 2
  done
  "$PY" app.py --connect-jackett && note "Add sites in Jackett's page: http://127.0.0.1:9117 > + Add indexer."
fi

# ---- App + start ------------------------------------------------------------
bold "8/8  BuzzTorrent app"
mkdir -p data
date > data/mac-setup-asked          # so Start BuzzTorrent doesn't ask these questions again
if "$PY" app.py --install-shortcuts >/dev/null 2>&1; then
  ok "BuzzTorrent added to your Applications folder (open it from Launchpad or Spotlight)"
else
  note "Couldn't add the app to Applications; use Start BuzzTorrent.command instead."
fi
chmod +x "Start BuzzTorrent.command" "Stop BuzzTorrent.command" 2>/dev/null

note "Your TV app and VR headset (BuzzTorrent VR on Meta Quest) can use BuzzTorrent on this Mac"
note "over the home Wi-Fi, after pairing once with a PIN."
if ask "Turn on TV / VR headset access on this Mac?"; then
  if askn "Also start BuzzTorrent in the background when you log in (so the headset always finds this Mac)?"; then
    "$PY" app.py --enable-tv --tv-autostart
  else
    "$PY" app.py --enable-tv
  fi
  note "If macOS asks whether \"python3\" may accept incoming network connections, click Allow."
fi

if ask "Start BuzzTorrent now?"; then
  nohup "$PY" launcher.pyw >/dev/null 2>&1 &
  ok "BuzzTorrent is starting in its own window."
fi
bold "Done."
note "Next time, open BuzzTorrent from Launchpad / Spotlight / your Applications folder."
note "TV or VR headset: BuzzTorrent > Settings > Living-room TV > turn on TV access."
note "  On the headset, pair once with this Mac (Choose another PC / + Mac), then switch"
note "  between your PC and this Mac with the PC / Mac toggle at the top of BuzzTorrent."
finish 0

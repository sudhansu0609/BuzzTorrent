#!/bin/bash
# BuzzTorrent for macOS, after `git clone`: installs everything it needs (Homebrew, Python,
# aria2, ClamAV + virus database, optional VLC/Chrome/Jackett), adds BuzzTorrent to
# ~/Applications and starts it. Each step asks first; safe to run again.
cd "$(dirname "$0")" || exit 1
chmod +x "Setup BuzzTorrent (Mac).command" "Start BuzzTorrent.command" "Stop BuzzTorrent.command" 2>/dev/null
xattr -d com.apple.quarantine ./*.command 2>/dev/null   # copied from a zip: let them run by double-click
exec bash "./Setup BuzzTorrent (Mac).command"

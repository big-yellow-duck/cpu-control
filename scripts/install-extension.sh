#!/usr/bin/env bash
# Install or update only the user extension; no system files or CPU changes.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
(( EUID != 0 )) || { echo 'Run as your desktop user.' >&2; exit 1; }
shell_major=$(gnome-shell --version | awk '{split($3,v,"."); print v[1]}')
[[ $shell_major == 50 ]] || { echo "This build requires GNOME Shell 50; detected $shell_major." >&2; exit 1; }
destination="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/cpu-control@local"
install -d -m 0755 "$destination"
install -m 0644 "$project"/extension/{extension.js,metadata.json,stylesheet.css} "$destination/"
if gnome-extensions enable cpu-control@local; then
    gnome-extensions info cpu-control@local
else
    /usr/bin/python3 "$project/scripts/enable-extension.py"
fi
echo 'Extension installed and enabled. Log out and back in to load updated JavaScript.'

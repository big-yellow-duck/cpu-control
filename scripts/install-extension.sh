#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install or update only the user extension; no system files or CPU changes.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
(( EUID != 0 )) || { echo 'Run as your desktop user.' >&2; exit 1; }
shell_major=$(gnome-shell --version | awk '{split($3,v,"."); print v[1]}')
[[ $shell_major == 50 ]] || { echo "This build requires GNOME Shell 50; detected $shell_major." >&2; exit 1; }
destination="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/cpu-control@big-yellow-duck.github.io"
install -d -m 0755 "$destination"
install -m 0644 "$project"/extension/{extension.js,metadata.json,stylesheet.css} "$destination/"
install -m 0644 "$project/LICENSE" "$destination/LICENSE"
if gnome-extensions enable cpu-control@big-yellow-duck.github.io; then
    gnome-extensions info cpu-control@big-yellow-duck.github.io
else
    /usr/bin/python3 "$project/scripts/enable-extension.py"
fi
echo 'Extension installed and enabled. Log out and back in to load updated JavaScript.'

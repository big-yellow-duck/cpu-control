#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if (( EUID == 0 )); then
    echo 'Run this as your desktop user.' >&2
    exit 1
fi
echo 'Restoring all CPUs before removing the privileged service and policies.'
pkexec /usr/bin/bash "$project/scripts/uninstall-system.sh"
gnome-extensions disable cpu-control@big-yellow-duck.github.io || true
/usr/bin/python3 - <<'PY'
from gi.repository import Gio
s = Gio.Settings.new('org.gnome.shell')
for key in ('enabled-extensions', 'disabled-extensions'):
    s.set_strv(key, [x for x in s.get_strv(key) if x != 'cpu-control@big-yellow-duck.github.io'])
Gio.Settings.sync()
PY
destination="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/cpu-control@big-yellow-duck.github.io"
rm -f -- "$destination/extension.js" "$destination/cpuState.js" "$destination/metadata.json" "$destination/stylesheet.css" "$destination/LICENSE"
rmdir -- "$destination" 2>/dev/null || true
echo 'CPU Control removed. Project sources retained.'

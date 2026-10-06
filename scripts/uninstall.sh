#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if (( EUID == 0 )); then
    echo 'Run this as your desktop user.' >&2
    exit 1
fi
echo 'Restoring all CPUs before removing the privileged service and policies.'
pkexec /usr/bin/bash "$project/scripts/uninstall-system.sh"
gnome-extensions disable cpu-control@local || true
/usr/bin/python3 - <<'PY'
from gi.repository import Gio
s = Gio.Settings.new('org.gnome.shell')
for key in ('enabled-extensions', 'disabled-extensions'):
    s.set_strv(key, [x for x in s.get_strv(key) if x != 'cpu-control@local'])
Gio.Settings.sync()
PY
destination="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/cpu-control@local"
rm -f -- "$destination/extension.js" "$destination/metadata.json" "$destination/stylesheet.css"
rmdir -- "$destination" 2>/dev/null || true
echo 'CPU Control removed. Project sources retained.'

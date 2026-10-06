#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if (( EUID == 0 )); then
    echo 'Run this script as your desktop user; it requests authentication for the system files.' >&2
    exit 1
fi
shell_major=$(gnome-shell --version | awk '{split($3,v,"."); print v[1]}')
if [[ $shell_major != 50 ]]; then
    echo "This build is tested for GNOME Shell 50; detected $shell_major." >&2
    exit 1
fi
/usr/bin/python3 -c 'from gi.repository import Gio, GLib' # already supplied by Bazzite
echo 'System installation: root-owned /etc/cpu-control helper, systemd unit,'
echo '/etc/dbus-1/system.d policy, /etc/polkit-1 action and local-user rule.'
echo 'Topology discovery briefly enables all CPUs, then restores their starting state.'
pkexec /usr/bin/bash "$project/scripts/install-system.sh" "$project" "$(id -un)"
"$project/scripts/install-extension.sh"

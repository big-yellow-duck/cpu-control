#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
(( EUID != 0 )) || { echo 'Run as your desktop user.' >&2; exit 1; }
echo 'Enable the installed TuneD and tuned-ppd services for GNOME power profiles.'
echo 'Install /etc/systemd/system/bazzite-hardware-setup.service.d/90-gnome-power-profiles.conf.'
echo 'Keep a record of original service states under /etc/gnome-power-profiles.'
pkexec /usr/bin/python3 -I -B "$project/scripts/power-profiles-system.py" install "$project"

#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
(( EUID != 0 )) || { echo 'Run as your desktop user.' >&2; exit 1; }
echo 'Remove the GNOME power-profile override and restore the original service states.'
pkexec /usr/bin/python3 -I -B "$project/scripts/power-profiles-system.py" uninstall "$project"

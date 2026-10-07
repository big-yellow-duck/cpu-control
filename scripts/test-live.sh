#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Temporarily changes real CPU availability; the root guard restores it afterward.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
(( EUID != 0 )) || { echo 'Run as your desktop user.' >&2; exit 1; }
"$project/scripts/package-extension.sh"
echo 'Testing real core/SMT changes and the extension in a separate headless GNOME Shell.'
echo 'A privileged guard will restore your exact initial online mask and kernel SMT control.'
/usr/bin/python3 -B "$project/tests/run_live.py"

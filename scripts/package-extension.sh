#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build only the files used by GNOME Shell; the helper is installed separately.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
npm --prefix "$project" run build
mkdir -p "$project/artifacts"
gnome-extensions pack "$project/dist" --force --out-dir="$project/artifacts" --extra-source="$project/dist/cpuState.js" --extra-source="$project/LICENSE"

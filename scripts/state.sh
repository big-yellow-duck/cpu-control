#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
busctl --json=short call io.github.big_yellow_duck.CpuControl1 /io/github/big_yellow_duck/CpuControl1 io.github.big_yellow_duck.CpuControl1 GetState |
    /usr/bin/python3 -c 'import json,sys; print(json.dumps(json.loads(json.load(sys.stdin)["data"][0]),indent=2))'

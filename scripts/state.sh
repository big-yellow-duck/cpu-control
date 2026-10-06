#!/usr/bin/env bash
set -euo pipefail
busctl --json=short call org.local.CpuControl1 /org/local/CpuControl1 org.local.CpuControl1 GetState |
    /usr/bin/python3 -c 'import json,sys; print(json.dumps(json.loads(json.load(sys.stdin)["data"][0]),indent=2))'

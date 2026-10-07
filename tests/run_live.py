#!/usr/bin/python3
# SPDX-License-Identifier: Apache-2.0
"""Run real D-Bus/Shell tests in the desktop session, with a separate root guard."""
import os
import signal
import subprocess
from pathlib import Path

project = Path(__file__).resolve().parents[1]
assert os.geteuid() != 0, "Run scripts/test-live.sh as your desktop user"


def run(command):
    process = subprocess.Popen(command, cwd=project, start_new_session=True)
    try:
        status = process.wait(timeout=120)
        if status:
            raise RuntimeError(f"Test exited with status {status}")
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


guard = subprocess.Popen(["/usr/bin/pkexec", "/usr/bin/python3", "-I", "-B", str(project / "tests/live_guard.py")],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
try:
    ready = guard.stdout.readline()
    print(ready, end="", flush=True)
    if not ready.startswith("READY:"):
        raise RuntimeError("Recovery guard did not start")
    run(["/usr/bin/python3", "-B", str(project / "tests/live_client.py")])
    run(["/usr/bin/dbus-run-session", "--", "/usr/bin/gnome-shell-test-tool", "--headless",
         "--disable-animations", "--extension", str(project / "artifacts/cpu-control@big-yellow-duck.github.io.shell-extension.zip"),
         str(project / "tests/shell-smoke.js")])
finally:
    output, _ = guard.communicate("restore\n", timeout=15)
    print(output, end="", flush=True)
    if guard.returncode:
        raise RuntimeError("CPU recovery guard failed")

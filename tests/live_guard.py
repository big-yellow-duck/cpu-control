#!/usr/bin/python3
"""Snapshot CPUs as root; restore on pipe closure, request, signal or timeout."""
import importlib.util
import os
import select
import signal
import sys
from pathlib import Path


def main():
    if os.geteuid() != 0:
        raise SystemExit("Use scripts/test-live.sh")
    spec = importlib.util.spec_from_file_location("controller", "/etc/cpu-control/cpu_control.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    controller = module.Controller(cache=Path("/run/cpu-control/topology.json"))
    original_online, original_smt = controller.online(), controller.smt_control()
    def interrupted(signum, _frame):
        raise InterruptedError(f"Interrupted by signal {signum}")

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        print(f"READY: online={sorted(original_online)} smt={original_smt}", flush=True)
        readable, _, _ = select.select([sys.stdin], [], [], 300)
        if readable:
            sys.stdin.readline()  # Any message or EOF requests restoration, never a command.
    finally:
        controller.restore_snapshot(original_online, original_smt)
        if controller.online() != original_online or controller.smt_control() != original_smt:
            raise RuntimeError("Original CPU state could not be restored")
        print(f"Restored: online={sorted(controller.online())} smt={controller.smt_control()}", flush=True)


if __name__ == "__main__":
    main()

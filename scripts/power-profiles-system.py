#!/usr/bin/python3
# SPDX-License-Identifier: Apache-2.0
"""Reversible opt-in to the installed Fedora GNOME power-profile backend."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

UNITS = ("tuned.service", "tuned-ppd.service")
BACKUP = Path("/etc/gnome-power-profiles/original.json")
DROPIN = Path("/etc/systemd/system/bazzite-hardware-setup.service.d/90-gnome-power-profiles.conf")


def run(*arguments, check=True):
    return subprocess.run(arguments, check=check, text=True, capture_output=True)


def state(unit):
    return {"enabled": run("systemctl", "is-enabled", unit, check=False).stdout.strip(),
            "active": run("systemctl", "is-active", unit, check=False).stdout.strip() == "active"}


def install(project):
    for unit in UNITS:
        if not (Path("/usr/lib/systemd/system") / unit).is_file():
            raise RuntimeError(f"{unit} is not installed; no package changes were made")
    if not Path("/usr/libexec/bazzite-hardware-setup").is_file():
        raise RuntimeError("This override is specific to Bazzite hardware setup")
    if not BACKUP.exists():
        if DROPIN.exists():
            raise RuntimeError(f"Existing unmanaged drop-in: {DROPIN}")
        BACKUP.parent.mkdir(mode=0o700)
        BACKUP.write_text(json.dumps({unit: state(unit) for unit in UNITS}, indent=2))
        BACKUP.chmod(0o600)
    DROPIN.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    shutil.copyfile(project / "systemd/bazzite-hardware-setup.service.d/90-gnome-power-profiles.conf", DROPIN)
    DROPIN.chmod(0o644)
    run("restorecon", "-RF", str(BACKUP.parent), str(DROPIN))
    run("systemctl", "daemon-reload")
    run("systemctl", "unmask", *UNITS)
    run("systemctl", "enable", *UNITS)
    run("systemctl", "start", "tuned-ppd.service")
    print("GNOME power profiles enabled through TuneD and tuned-ppd.")


def uninstall():
    if not BACKUP.exists():
        raise RuntimeError("No saved power-profile installation state")
    saved = json.loads(BACKUP.read_text())
    DROPIN.unlink(missing_ok=True)
    try:
        DROPIN.parent.rmdir()
    except OSError:
        pass
    run("systemctl", "stop", "tuned-ppd.service", "tuned.service")
    run("systemctl", "disable", *UNITS)
    for unit in UNITS:
        previous = saved[unit]
        enabled = previous["enabled"]
        if enabled in ("masked", "masked-runtime"):
            arguments = ("--runtime",) if enabled == "masked-runtime" else ()
            run("systemctl", "mask", *arguments, unit)
        elif enabled in ("enabled", "enabled-runtime"):
            arguments = ("--runtime",) if enabled == "enabled-runtime" else ()
            run("systemctl", "enable", *arguments, unit)
    run("systemctl", "daemon-reload")
    for unit in UNITS:
        if saved[unit]["active"]:
            run("systemctl", "start", unit)
    BACKUP.unlink()
    BACKUP.parent.rmdir()
    print("Original GNOME power-profile service configuration restored.")


if __name__ == "__main__":
    if os.geteuid() != 0 or len(sys.argv) != 3:
        raise SystemExit("Use scripts/install-power-profiles.sh or scripts/uninstall-power-profiles.sh")
    if sys.argv[1] == "install":
        install(Path(sys.argv[2]).resolve())
    elif sys.argv[1] == "uninstall":
        uninstall()
    else:
        raise SystemExit("Unknown operation")

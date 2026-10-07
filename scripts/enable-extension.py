#!/usr/bin/python3
# SPDX-License-Identifier: Apache-2.0
"""Enable for next login when Shell hasn't discovered a newly installed extension."""
from gi.repository import Gio

settings = Gio.Settings.new("org.gnome.shell")
uuid = "cpu-control@big-yellow-duck.github.io"
enabled = settings.get_strv("enabled-extensions")
if uuid not in enabled:
    settings.set_strv("enabled-extensions", enabled + [uuid])
disabled = settings.get_strv("disabled-extensions")
if uuid in disabled:
    settings.set_strv("disabled-extensions", [item for item in disabled if item != uuid])
Gio.Settings.sync()

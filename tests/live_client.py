#!/usr/bin/python3
# SPDX-License-Identifier: Apache-2.0
"""Real system D-Bus requests as the unprivileged desktop user."""
import json
import os
from pathlib import Path
from gi.repository import Gio, GLib

BUS = "io.github.big_yellow_duck.CpuControl1"
PATH = "/io/github/big_yellow_duck/CpuControl1"
ROOT = Path("/sys/devices/system/cpu")
connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def cpu_list(text):
    result = set()
    for part in text.strip().split(","):
        bounds = part.split("-")
        result.update(range(int(bounds[0]), int(bounds[-1]) + 1))
    return result


def call(method, parameters=None):
    result = connection.call_sync(BUS, PATH, BUS, method, parameters,
                                  GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, 75000, None)
    return json.loads(result.unpack()[0])


def verify(state, count, smt, cores):
    online = cpu_list((ROOT / "online").read_text())
    active = [threads for threads in cores if online.intersection(threads)]
    assert set(state["online_cpus"]) == online
    assert state["physical_cores"] == len(active) == count
    assert 0 in online
    for threads in active:
        if smt:
            assert online.intersection(threads) == threads
        else:
            assert len(online.intersection(threads)) == 1
    if state["smt_supported"]:
        assert state["smt_enabled"] == smt
        assert not state["smt_mixed"]
        assert (ROOT / "smt/active").read_text().strip() == ("1" if smt else "0")
    print(f"PASS: {count} physical cores, SMT {'ON' if smt else 'OFF'}, {len(online)} threads", flush=True)


assert os.geteuid() != 0, "Live D-Bus tests must run unprivileged"
initial = call("GetState")
assert initial["ready"]
all_state = call("RestoreAll")
cores = {}
for cpu in all_state["online_cpus"]:
    topology = ROOT / f"cpu{cpu}" / "topology"
    threads = frozenset(cpu_list((topology / "thread_siblings_list").read_text()))
    cores[threads] = threads
cores = list(cores.values())
assert len(cores) == all_state["total_cores"]
verify(all_state, len(cores), all_state["smt_supported"], cores)
for count in [c for c in initial["choices"] if c >= min(4, len(cores))]:
    verify(call("SetConfiguration", GLib.Variant("(ub)", (count, True))), count, all_state["smt_supported"], cores)
    verify(call("SetConfiguration", GLib.Variant("(ub)", (count, False))), count, False, cores)
    verify(call("SetConfiguration", GLib.Variant("(ub)", (count, True))), count, all_state["smt_supported"], cores)
before_invalid = call("GetState")["online_cpus"]
try:
    call("SetConfiguration", GLib.Variant("(ub)", (0, True)))
except GLib.Error:
    pass
else:
    raise AssertionError("Invalid core count was accepted")
assert call("GetState")["online_cpus"] == before_invalid
print("PASS: invalid count rejected without changing CPUs; helper remains responsive", flush=True)
verify(call("RestoreAll"), len(cores), all_state["smt_supported"], cores)

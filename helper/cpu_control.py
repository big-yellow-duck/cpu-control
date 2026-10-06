#!/usr/bin/python3
"""Restricted CPU hotplug controller. No subprocesses or caller-supplied paths."""
from __future__ import annotations

import json
import logging
import signal
from pathlib import Path


BUS_NAME = "org.local.CpuControl1"
OBJECT_PATH = "/org/local/CpuControl1"
ACTION = "org.local.cpu-control.configure"


def cpu_list(value: str) -> set[int]:
    result = set()
    for part in value.strip().split(","):
        if not part:
            continue
        limits = part.split("-")
        start = int(limits[0])
        end = int(limits[-1])
        if start < 0 or end < start:
            raise ValueError("Invalid CPU list")
        result.update(range(start, end + 1))
    return result


class Controller:
    def __init__(self, root=Path("/sys/devices/system/cpu"), cache=None):
        self.root = root
        self.cache = cache
        self.cores = []
        self.pinned = {0}
        self.last_error = ""
        self._present = self.present()
        self.pinned.update(cpu for cpu in self._present if not self.path(cpu).exists())
        if cache and cache.exists():
            try:
                saved = json.loads(cache.read_text())
                if set(saved["present"]) == self._present:
                    self.validate(saved["cores"])
                    self.cores = saved["cores"]
            except (OSError, ValueError, KeyError, TypeError):
                logging.exception("Ignoring invalid topology cache")
        if not self.cores:
            try:
                self.cores = self.scan()
                self.save()
            except (OSError, ValueError):
                # Starting the service never changes CPU availability.
                pass

    def path(self, cpu):
        return self.root / f"cpu{cpu}" / "online"

    def present(self):
        return cpu_list((self.root / "present").read_text())

    def online(self):
        return cpu_list((self.root / "online").read_text()) & self.present()

    def smt_control(self):
        path = self.root / "smt/control"
        return path.read_text().strip() if path.exists() else "notsupported"

    def control(self, value):
        if self.smt_control() != value:
            (self.root / "smt/control").write_text(value)

    def validate(self, cores):
        seen = set()
        for core in cores:
            threads = core["threads"]
            if not threads or any(type(cpu) is not int or cpu < 0 for cpu in threads):
                raise ValueError("Invalid core threads")
            if len(set(threads)) != len(threads) or seen.intersection(threads):
                raise ValueError("Overlapping core topology")
            seen.update(threads)
        if seen != self.present():
            raise ValueError("Incomplete physical CPU topology; detect topology first")

    def scan(self):
        if self.online() != self.present():
            raise ValueError("Offline CPU topology unavailable; detect topology first")
        groups = {}
        for cpu in sorted(self.present()):
            topo = self.root / f"cpu{cpu}" / "topology"
            threads = tuple(sorted(cpu_list((topo / "thread_siblings_list").read_text()) & self.present()))
            package = int((topo / "physical_package_id").read_text())
            core_id = int((topo / "core_id").read_text())
            if cpu not in threads or package < 0 or core_id < 0:
                raise ValueError("Invalid sysfs topology")
            info = {"package": package, "core_id": core_id, "threads": list(threads)}
            if threads in groups and groups[threads] != info:
                raise ValueError("Inconsistent sibling topology")
            groups[threads] = info
        cores = sorted(groups.values(), key=lambda c: (c["package"], c["core_id"], c["threads"][0]))
        self.validate(cores)
        return cores

    def save(self):
        if self.cache:
            temporary = self.cache.with_suffix(".tmp")
            temporary.write_text(json.dumps({"present": sorted(self.present()), "cores": self.cores}))
            temporary.replace(self.cache)

    def write_cpu(self, cpu, enabled):
        if cpu not in self.present():
            raise ValueError("CPU is no longer present")
        if not enabled and cpu in self.pinned:
            raise ValueError(f"CPU{cpu} must remain online")
        path = self.path(cpu)
        if not path.exists():
            if enabled:
                return
            raise ValueError(f"CPU{cpu} has no hotplug control")
        try:
            path.write_text("1" if enabled else "0")
        except OSError:
            if not enabled:
                # Never repeatedly try a CPU the kernel rejected.
                self.pinned.add(cpu)
            raise

    def apply_mask(self, target):
        online = self.online()
        for cpu in sorted(target - online):
            self.write_cpu(cpu, True)
        for cpu in sorted(self.online() - target, reverse=True):
            self.write_cpu(cpu, False)
        if self.online() != target:
            raise RuntimeError("CPU availability changed concurrently; operation rolled back")

    def restore_snapshot(self, online, smt):
        # SMT control can itself hotplug threads, so restore it before the mask.
        if smt in ("on", "off"):
            self.control(smt)
        self.apply_mask(online)

    def transaction(self, operation):
        before, smt = self.online(), self.smt_control()
        try:
            operation()
            self.last_error = ""
        except Exception as exc:
            message = str(exc)
            try:
                self.restore_snapshot(before, smt)
            except Exception as rollback:
                message += f"; rollback failed: {rollback}. Use All cores to recover."
            self.last_error = message
            raise RuntimeError(message) from exc

    def discover(self):
        before, smt = self.online(), self.smt_control()
        discovered = []

        def probe():
            nonlocal discovered
            if smt == "off":
                self.control("on")
            self.apply_mask(self.present())
            discovered = self.scan()
            self.restore_snapshot(before, smt)

        self.transaction(probe)
        self.cores = discovered
        self._present = self.present()
        self.pinned.intersection_update(self._present)
        self.pinned.update(cpu for cpu in self._present if cpu == 0 or not self.path(cpu).exists())
        self.save()
        return self.state()

    def configuration(self, count, smt):
        if type(count) is not int or type(smt) is not bool:
            raise ValueError("Expected physical core count and boolean SMT state")
        self.validate(self.cores)
        if not 1 <= count <= len(self.cores):
            raise ValueError("Physical core count is out of range")
        required = [core for core in self.cores if self.pinned.intersection(core["threads"])]
        if count < len(required):
            raise ValueError(f"At least {len(required)} cores must remain online")
        selected = required + [core for core in self.cores if core not in required][:count - len(required)]
        target = set()
        for core in selected:
            mandatory = self.pinned.intersection(core["threads"])
            if not smt and len(mandatory) > 1:
                raise ValueError("SMT cannot be disabled on a core with multiple fixed threads")
            target.update(core["threads"] if smt else mandatory or {min(core["threads"])})

        def apply():
            if smt and self.smt_control() == "off":
                self.control("on")
            self.apply_mask(target)

        self.transaction(apply)
        return self.state()

    def restore_all(self):
        def apply():
            if self.smt_control() == "off":
                self.control("on")
            self.apply_mask(self.present())
        self.transaction(apply)
        if not self.cores or self.present() != self._present:
            self.cores = self.scan()
            self._present = self.present()
            self.pinned.intersection_update(self._present)
            self.pinned.update(cpu for cpu in self._present if cpu == 0 or not self.path(cpu).exists())
            self.save()
        return self.state()

    def state(self):
        present, online = self.present(), self.online()
        valid = bool(self.cores) and present == self._present
        active = [core for core in self.cores if online.intersection(core["threads"])] if valid else []
        threaded = [core for core in active if len(core["threads"]) > 1]
        any_smt = any(len(online.intersection(core["threads"])) > 1 for core in threaded)
        full_smt = bool(threaded) and all(set(core["threads"]) <= online for core in threaded)
        required = sum(bool(self.pinned.intersection(core["threads"])) for core in self.cores)
        total = len(self.cores) if valid else 0
        # Short menu derived from topology, while the API permits every count.
        choices = {1} | set(range(2, min(total, 9), 2)) | set(range(12, total, 4))
        if active:
            choices.add(len(active))
        return {
            "ready": valid, "physical_cores": len(active), "total_cores": total,
            "online_cpus": sorted(online), "total_threads": len(present),
            "smt_enabled": any_smt, "smt_mixed": any_smt and not full_smt,
            "smt_supported": any(len(core["threads"]) > 1 for core in self.cores),
            "smt_available": self.smt_control() not in ("forceoff", "notsupported", "notimplemented"),
            "smt_control": self.smt_control(), "pinned_cpus": sorted(self.pinned),
            "choices": sorted(c for c in choices if required <= c < total),
            "error": self.last_error,
        }


def serve():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib, GLibUnix

    controller = Controller(cache=Path("/run/cpu-control/topology.json"))
    connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    xml = Path(__file__).with_name("org.local.CpuControl1.xml").read_text()
    interface = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]
    loop = GLib.MainLoop()
    busy = False
    last = ""

    def state_json():
        return json.dumps(controller.state(), sort_keys=True)

    def publish():
        nonlocal last
        try:
            state = state_json()
            if state != last:
                last = state
                connection.emit_signal(None, OBJECT_PATH, BUS_NAME, "StateChanged", GLib.Variant("(s)", (state,)))
        except Exception:
            logging.exception("Cannot read CPU state")
        return GLib.SOURCE_CONTINUE

    def error(invocation, suffix, message):
        invocation.return_dbus_error(f"{BUS_NAME}.Error.{suffix}", message)

    def handle(conn, sender, path, iface, method, parameters, invocation):
        nonlocal busy
        if method == "GetState":
            try:
                invocation.return_value(GLib.Variant("(s)", (state_json(),)))
            except Exception as exc:
                error(invocation, "Unavailable", str(exc))
            return
        if method not in ("Discover", "SetConfiguration", "RestoreAll"):
            error(invocation, "Invalid", "Unknown operation")
            return
        if busy:
            error(invocation, "Busy", "Another CPU change is in progress")
            return
        busy = True
        args = parameters.unpack()
        subject = ("system-bus-name", {"name": GLib.Variant("s", sender)})
        request = GLib.Variant("((sa{sv})sa{ss}us)", (subject, ACTION, {}, 1, ""))

        def authorized(bus, result):
            nonlocal busy
            try:
                allowed, _, _ = bus.call_finish(result).unpack()[0]
                if not allowed:
                    error(invocation, "Denied", "CPU change was not authorized")
                    return
                if method == "SetConfiguration":
                    state = controller.configuration(*args)
                elif method == "RestoreAll":
                    state = controller.restore_all()
                else:
                    state = controller.discover()
                invocation.return_value(GLib.Variant("(s)", (json.dumps(state),)))
            except Exception as exc:
                logging.exception("CPU operation failed")
                error(invocation, "Failed", str(exc))
            finally:
                busy = False
                publish()

        connection.call("org.freedesktop.PolicyKit1", "/org/freedesktop/PolicyKit1/Authority",
                        "org.freedesktop.PolicyKit1.Authority", "CheckAuthorization", request,
                        GLib.VariantType.new("((bba{ss}))"), Gio.DBusCallFlags.NONE, 60000, None, authorized)

    connection.register_object_with_closures2(OBJECT_PATH, interface, handle, None, None)
    def lost(*_):
        logging.error("D-Bus service name lost")
        loop.quit()
    owner = Gio.bus_own_name_on_connection(connection, BUS_NAME, Gio.BusNameOwnerFlags.NONE, None, lost)
    GLib.timeout_add_seconds(2, publish)
    for sig in (signal.SIGTERM, signal.SIGINT):
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (loop.quit(), GLib.SOURCE_REMOVE)[1])
    loop.run()
    Gio.bus_unown_name(owner)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()

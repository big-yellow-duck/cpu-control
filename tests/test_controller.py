# SPDX-License-Identifier: Apache-2.0
"""Exercise topology, ordering, recovery and external changes with fake sysfs."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("cpu_control", Path(__file__).parents[1] / "helper/cpu_control.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeController(module.Controller):
    def __init__(self, root, cache=None):
        self.writes = []
        self.reject = set()
        super().__init__(root, cache)

    def write_cpu(self, cpu, enabled):
        self.writes.append((cpu, enabled))
        if (cpu, enabled) in self.reject:
            if not enabled:
                self.pinned.add(cpu)
            raise OSError(f"Kernel rejected CPU{cpu}")
        super().write_cpu(cpu, enabled)
        online = self.online()
        online.add(cpu) if enabled else online.discard(cpu)
        (self.root / "online").write_text(",".join(map(str, sorted(online))))

    def control(self, value):
        old = self.smt_control()
        super().control(value)
        if old != value:
            # Linux's global SMT knob changes the online mask too.
            online = self.online()
            if value == "on":
                online.update(self.present())
            else:
                online.difference_update({7, 2, 5, 6})
            (self.root / "online").write_text(",".join(map(str, sorted(online))))


class TopologyTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "present").write_text("0-7")
        (self.root / "online").write_text("0-7")
        (self.root / "smt").mkdir()
        (self.root / "smt/control").write_text("on")
        # Deliberately shuffled numbering, with duplicate core_id across sockets.
        for package, core_id, threads in [(0, 9, [0, 7]), (0, 3, [4, 2]), (1, 3, [1, 5]), (1, 9, [3, 6])]:
            for cpu in threads:
                path = self.root / f"cpu{cpu}"
                (path / "topology").mkdir(parents=True)
                for name, value in {"physical_package_id": str(package), "core_id": str(core_id),
                                    "thread_siblings_list": ",".join(map(str, threads))}.items():
                    (path / "topology" / name).write_text(value)
                if cpu:
                    (path / "online").write_text("1")
        self.controller = FakeController(self.root)

    def test_physical_selection_and_smt_preserve_count(self):
        c = self.controller
        c.configuration(2, True)
        self.assertEqual(c.online(), {0, 7, 2, 4})
        self.assertEqual(c.state()["physical_cores"], 2)
        self.assertTrue(c.state()["smt_enabled"])
        c.configuration(2, False)
        self.assertEqual(c.online(), {0, 2})
        self.assertEqual(c.state()["physical_cores"], 2)
        c.configuration(2, True)
        self.assertEqual(c.online(), {0, 7, 2, 4})
        self.assertNotIn((0, False), c.writes)

    def test_failure_rolls_back_and_pins_rejected_cpu(self):
        c = self.controller
        c.reject = {(5, False)}
        with self.assertRaisesRegex(RuntimeError, "rejected"):
            c.configuration(1, False)
        self.assertEqual(c.online(), set(range(8)))
        self.assertIn(5, c.pinned)
        rejected_attempts = c.writes.count((5, False))
        c.configuration(2, True)
        self.assertEqual(c.writes.count((5, False)), rejected_attempts)
        self.assertEqual(c.online(), {0, 7, 1, 5})

    def test_enable_before_disable_when_selection_changes(self):
        c = self.controller
        c.configuration(1, False)
        # Simulate a different core retained externally in addition to CPU0.
        (self.root / "online").write_text("0,1")
        c.writes.clear()
        c.configuration(2, False)
        self.assertLess(c.writes.index((2, True)), c.writes.index((1, False)))

    def test_discovery_restores_mask_and_kernel_smt_control(self):
        c = self.controller
        c.control("off")
        c.apply_mask({0, 1})
        c.cores = []
        c.discover()
        self.assertEqual(c.online(), {0, 1})
        self.assertEqual(c.smt_control(), "off")
        self.assertEqual(c.state()["total_cores"], 4)

    def test_restore_all_enables_global_smt(self):
        c = self.controller
        c.control("off")
        c.apply_mask({0})
        c.restore_all()
        self.assertEqual(c.online(), set(range(8)))
        self.assertEqual(c.smt_control(), "on")

    def test_external_changes_and_mixed_smt(self):
        (self.root / "online").write_text("0,7,1")
        state = self.controller.state()
        self.assertEqual(state["physical_cores"], 2)
        self.assertTrue(state["smt_mixed"])

    def test_invalid_request_does_not_write(self):
        for count in (0, 5):
            with self.assertRaises(ValueError):
                self.controller.configuration(count, True)
        self.assertEqual(self.controller.writes, [])

    def test_startup_with_offline_cpu_never_changes_mask(self):
        (self.root / "online").write_text("0")
        c = FakeController(self.root)
        self.assertEqual(c.online(), {0})
        self.assertEqual(c.writes, [])
        self.assertFalse(c.state()["ready"])

    def test_cached_topology_survives_service_restart_with_offline_cpus(self):
        cache = self.root / "cache.json"
        c = FakeController(self.root, cache)
        c.configuration(1, False)
        restarted = FakeController(self.root, cache)
        self.assertTrue(restarted.state()["ready"])
        self.assertEqual(restarted.state()["total_cores"], 4)
        self.assertEqual(restarted.writes, [])

    def test_discovery_refreshes_changed_present_cpu_set(self):
        (self.root / "present").write_text("0-6")
        self.assertFalse(self.controller.state()["ready"])
        self.controller.discover()
        self.assertTrue(self.controller.state()["ready"])
        self.assertEqual(self.controller.state()["total_threads"], 7)

    def test_restore_all_refreshes_changed_present_cpu_set(self):
        (self.root / "present").write_text("0-6")
        self.assertFalse(self.controller.state()["ready"])
        self.controller.restore_all()
        self.assertTrue(self.controller.state()["ready"])
        self.assertEqual(self.controller.online(), set(range(7)))


if __name__ == "__main__":
    unittest.main()

# CPU Control

A GNOME Shell 50 top-bar menu for selecting **physical CPU cores** and turning **SMT ON/OFF**, backed by a small, polkit-protected system D-Bus service. For Linux desktops running GNOME Shell 50. Tested on Bazzite GNOME; other distributions must supply the dependencies below. The installer does not modify `/usr`.

## Menu

The top bar shows `CPU 8`, for example. Its menu shows the active/total physical-core count, a radio selector, **All cores**, an SMT switch, and the number of online logical threads. Counts are generated from the detected topology: 1, even counts through 8, then increments of 4 below the total. The currently active count is also included. The helper API accepts every valid physical-core count.

Selecting 8 with SMT ON enables every sibling thread on 8 physical cores. SMT OFF leaves one thread on each of those 8 cores. **All cores restores every present logical CPU and enables SMT**; to use all physical cores with SMT OFF, choose All cores, then switch SMT off.

The SMT switch keeps the menu open when clicked or activated with Enter or Space. Controls briefly disable while applying the change, then show the updated thread count, preserving the selected physical-core count.

The menu observes helper signals every two seconds and refreshes on opening and every five seconds. External CPU changes, partial SMT configurations, and helper restarts are reflected automatically. Disabling the extension leaves the current CPU configuration in place.

## Installation

Source installation requires Node.js 22 or newer and npm to compile the TypeScript extension. Run from your normal GNOME desktop account:

```sh
npm ci
./scripts/install.sh
```

An administrator authentication dialog installs the system files. The script then copies and enables the local extension. If GNOME has not discovered a new extension yet, log out and back in; the script enables it for that session. GNOME 50 uses Wayland and cannot restart Shell in place.

Dependencies: Python 3 with PyGObject (Gio and GLib), D-Bus, systemd, polkit with `pkexec`, and the GNOME extension tools. Bazzite supplies these components without package layering. This installer requires GNOME Shell 50 and a polkit version supporting `/etc/polkit-1/actions` (verified on Bazzite's polkit 127).

Installed files:

| Location | Purpose |
| --- | --- |
| `~/.local/share/gnome-shell/extensions/cpu-control@big-yellow-duck.github.io/` | Extension JavaScript, metadata and CSS |
| `/etc/cpu-control/` | Root-owned Python helper and D-Bus interface |
| `/etc/systemd/system/cpu-control.service` | Root service and sandbox settings |
| `/etc/dbus-1/system.d/io.github.big_yellow_duck.CpuControl1.conf` | System-bus access policy |
| `/etc/polkit-1/actions/io.github.big_yellow_duck.cpu-control.policy` | Single configuration action |
| `/etc/polkit-1/rules.d/49-cpu-control.rules` | Allow only the installing user in an active local session |
| `/run/cpu-control/topology.json` | Root-owned topology cache, removed on reboot |

Installation deliberately discovers topology by temporarily enabling all CPUs and restoring the original online mask and kernel SMT control. It never persists a reduced core count. The enabled service starts at boot but only **reads** CPU state until a configuration request arrives. If complete topology is available at startup, it caches it without hotplug. If CPUs were already offlined and topology is missing, the menu offers **Detect CPU topology…** or **All cores**.

Run the installer again to update all files. For extension-only updates, use `./scripts/install-extension.sh`; this updates your user files without changing the helper or CPU configuration. Log out and back in to load updated JavaScript in GNOME Shell. System files are copies owned by root; the service does not execute code from this working directory or your home directory. Remove it with:

```sh
./scripts/uninstall.sh
```

Uninstallation first restores all CPUs, then removes the service, its policies, runtime cache and extension. It stops if restoration fails so recovery remains available. Project source files are retained.

## Topology and safety

Topology comes from `physical_package_id`, `core_id`, and `thread_siblings_list` for every present CPU. Sibling groups are the identity of a physical core; numbering is never assumed. Groups must partition the complete present CPU set with consistent package/core identifiers. This also distinguishes repeated core IDs on separate sockets.

CPU0 and CPUs without an `online` control always remain online. Their physical cores are selected first, then remaining cores in package/core order. Required logical threads are enabled before surplus threads are removed. If Linux rejects offlining another CPU, that CPU is pinned for the remainder of the helper process; the failed operation rolls back and later requests keep its core. Errors are reported through D-Bus and the menu remains usable. Rollback failures report the problem and leave All cores available.

SMT switching primarily writes `/sys/devices/system/cpu/cpu*/online`. If the kernel global SMT control is `off`, SMT ON first sets `/sys/devices/system/cpu/smt/control` to `on`, then applies the requested physical-core/thread mask. SMT OFF offlines sibling CPUs individually, so global `smt/control` can remain `on` while `smt/active` is `0`. `forceoff` cannot be overridden. On systems where kernel/firmware forbids enabling CPUs, the helper reports the rejection.

Operations are serialized in the helper. External hotplug is detected at the end of an operation, but another independent CPU controller can still compete with this extension. Physical hot-add/removal invalidates the cache and requires topology discovery. Selection favors package/core order; it does not implement performance/efficiency-core preferences or workload migration policies.

## Security and D-Bus

The extension sends only typed D-Bus requests. It runs no `sudo`/`pkexec`, executes no privileged commands, and writes no sysfs files. The helper exposes four methods on `io.github.big_yellow_duck.CpuControl1`, object `/io/github/big_yellow_duck/CpuControl1`:

| Method | Arguments | Behavior |
| --- | --- | --- |
| `GetState` | none | Read current topology/online state as JSON; no authorization required |
| `SetConfiguration` | unsigned physical-core count, boolean SMT | Change only CPU availability |
| `RestoreAll` | none | Enable every present CPU, including SMT siblings |
| `Discover` | none | Probe complete topology and restore the starting CPU configuration |

All changing methods check `io.github.big_yellow_duck.cpu-control.configure` through polkit using the actual D-Bus sender's unique bus name. No caller-supplied paths, commands or executables are accepted. The local rule allows the installing user in an active local session; other active users require administrative authentication, and inactive/remote users are denied by default. The permission applies to applications in that user's session, not exclusively the extension.

The service has a read-only filesystem with write exceptions for the CPU sysfs subtree and its runtime directory, no capabilities, no home access, no new privileges, and only UNIX-domain networking. Source files remain in this project for review and reproducible installation.

## Diagnostics and tests

```sh
./scripts/state.sh
systemctl status cpu-control.service
journalctl -u cpu-control.service -b
gnome-extensions info cpu-control@big-yellow-duck.github.io
python3 -m unittest discover -s tests -v
```

For an integration test on real hardware, after installation:

```sh
./scripts/test-live.sh
```

This deliberately changes CPU availability. It makes D-Bus requests as your desktop user and runs the extension in a separate headless GNOME Shell using GNOME's own test tool. A separately authenticated root guard snapshots the exact online CPU mask and kernel SMT control and restores them on completion, failure, interruption, or test-process exit. Run it from an active local GNOME session. It does not restart your main desktop.

Verified locally on GNOME Shell 50.5 with 8 physical cores / 16 threads: 4, 6 and 8 physical cores with SMT ON/OFF; All cores; invalid requests leaving CPUs unchanged; native radio/switch callbacks; menu recovery after errors; and extension disable/re-enable. The integration guard restored the initial 8-online-thread, SMT-off state. The fake-sysfs tests additionally cover shuffled CPU numbering, separate sockets, rejected offlining, external state changes, topology-cache reuse, and changes to the present CPU set.

Command-line recovery:

```sh
busctl call io.github.big_yellow_duck.CpuControl1 /io/github/big_yellow_duck/CpuControl1 io.github.big_yellow_duck.CpuControl1 RestoreAll
```

If the helper is unavailable, the kernel hotplug controls remain usable through your usual administrative tools. Reboot also returns CPU availability to the system's existing boot defaults.

Implementation references: [GNOME 50 extension guide](https://gjs.guide/extensions/upgrading/gnome-shell-50.html), [native popup menus](https://gjs.guide/extensions/topics/popup-menu.html), [kernel CPU topology](https://www.kernel.org/doc/html/latest/admin-guide/cputopology.html), and [polkit architecture](https://polkit.pages.freedesktop.org/polkit/polkit.8.html).

## Sharing the extension

Build the GNOME extension archive from TypeScript with:

```sh
npm ci
./scripts/package-extension.sh
```

The ZIP is written to `artifacts/cpu-control@big-yellow-duck.github.io.shell-extension.zip`. It contains only the compiled JavaScript, runtime metadata and CSS and the Apache 2.0 license. Install the system helper first with `./scripts/install.sh`; installing the ZIP alone does not install the privileged helper. Uploading to extensions.gnome.org requires a separate review; packaging does not establish approval or compatibility beyond GNOME 50.

The extension UUID uses the project owner's GitHub namespace. The D-Bus interface and policy filenames use `io.github.big_yellow_duck`; underscores replace the hyphens in the GitHub username because D-Bus interface names do not permit hyphens.

For an existing installation using `cpu-control@local` / `org.local.CpuControl1`, run that version's `./scripts/uninstall.sh` before installing this version. This restores all CPUs and removes the old policies.

The optional `install-power-profiles.sh` and `uninstall-power-profiles.sh` scripts are Bazzite-specific utilities, independent of CPU Control installation. Their Bazzite systemd drop-in name identifies the service they modify and is intentionally retained.

## License

CPU Control is licensed under the [Apache License 2.0](LICENSE) (`Apache-2.0`).

## TypeScript development

The extension source lives in `extension/extension.ts`, with its validated helper-state contract in `extension/cpuState.ts`. GNOME Shell 50 and GJS API typings come from `@girs`. Strict TypeScript checking covers UI fields, nullable state, D-Bus method names and request tuples, and asynchronous replies.

```sh
npm ci
npm run check
npm run build
npm test
```

The build emits readable ES modules into `dist/` and copies metadata, CSS and the license there. Generated output and `node_modules/` are ignored by Git. Installation, packaging and live tests build from the TypeScript source; GNOME Shell runs the resulting JavaScript and does not need Node.js at runtime.

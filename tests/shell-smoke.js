// SPDX-License-Identifier: Apache-2.0
// Run by GNOME's own test tool in a separate headless Shell, under live_guard.py.
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';

export const METRICS = {};

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

async function until(predicate, message) {
    for (let attempt = 0; attempt < 100; attempt++) {
        if (predicate())
            return;
        await Scripting.sleep(100);
    }
    throw new Error(message);
}

export async function run() {
    const uuid = 'cpu-control@big-yellow-duck.github.io';
    await until(() => Main.extensionManager.lookup(uuid)?.stateObj?._state?.ready,
        'Extension did not load with valid topology');
    const extension = Main.extensionManager.lookup(uuid).stateObj;
    Main.overview.hide();
    await until(() => !Main.overview.visible && !Main.layoutManager._startingUp,
        'Shell startup did not finish');
    assert(extension._enabled, 'Extension must be enabled');
    assert(Main.panel.statusArea[uuid] === extension._button, 'Top bar button is missing');
    assert(extension._smt.sensitive, 'SMT switch should be available');
    extension._button.menu.open();
    await Scripting.sleep(300);
    assert(extension._smt.mapped, 'SMT switch is not mapped in the open menu');
    const count = extension._state.choices.find(value => value >= 4) ?? extension._state.choices[0];
    const item = extension._counts.find(([value]) => value === count)[1];
    item.activate(null);
    await until(() => !extension._busy && extension._state.physical_cores === count,
        'Radio selector did not apply the physical core count');
    extension._button.menu.open();
    await Scripting.sleep(300);
    let closes = 0;
    const openSignal = extension._button.menu.connect('open-state-changed', (_menu, open) => {
        if (!open)
            closes++;
    });
    try {
        for (let attempt = 0; attempt < 2; attempt++) {
            const smt = extension._state.smt_enabled;
            // Use the activation callback shared by clicks and keyboard input,
            // rather than toggle(), which bypasses GNOME's menu-close behavior.
            extension._smt.activate(null);
            assert(extension._button.menu.isOpen && closes === 0,
                'SMT activation closed the menu while applying');
            await until(() => !extension._busy && extension._state.smt_enabled === !smt,
                'SMT activation did not apply');
            assert(extension._state.physical_cores === count, 'SMT changed physical core count');
            assert(extension._button.menu.isOpen && closes === 0,
                'SMT activation closed the menu after applying');
            assert(extension._smt.sensitive, 'SMT switch remained disabled');
        }
        print('PASS: SMT activation in both directions keeps the menu open');
    } finally {
        extension._button.menu.disconnect(openSignal);
    }
    extension._all.activate(null);
    await until(() => !extension._busy && extension._state.online_cpus.length === extension._state.total_threads,
        'All cores did not restore every logical CPU');
    // Invalid requests must recover UI sensitivity after an error.
    await extension._change('SetConfiguration', new GLib.Variant('(ub)', [0, true]));
    assert(!extension._busy && extension._all.sensitive, 'Menu stuck after an error');
    const state = extension._state;
    let changes = 0;
    const change = extension._change;
    extension._change = () => { changes++; };
    extension._render({...state, smt_enabled: false});
    extension._render(state);
    extension._change = change;
    assert(changes === 0, 'Rendering SMT state triggered a configuration request');
    Main.extensionManager.disableExtension(uuid);
    await until(() => !extension._enabled, 'Extension did not disable');
    assert(!Main.panel.statusArea[uuid], 'Top bar button leaked after disable');
    Main.extensionManager.enableExtension(uuid);
    await until(() => extension._enabled && extension._state?.ready, 'Extension did not re-enable');
    assert(extension._all.sensitive, 'Menu did not recover on re-enable');
    print('PASS: GNOME 50 radio selection, SMT toggle, All cores, error recovery and disable/re-enable');
}

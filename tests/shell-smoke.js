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
    const uuid = 'cpu-control@local';
    await until(() => Main.extensionManager.lookup(uuid)?.stateObj?._state?.ready,
        'Extension did not load with valid topology');
    const extension = Main.extensionManager.lookup(uuid).stateObj;
    assert(extension._enabled, 'Extension must be enabled');
    assert(Main.panel.statusArea[uuid] === extension._button, 'Top bar button is missing');
    assert(extension._smt.sensitive, 'SMT switch should be available');
    extension._button.menu.open();
    await Scripting.sleep(300);
    const count = extension._state.choices.find(value => value >= 4) ?? extension._state.choices[0];
    const item = extension._counts.find(([value]) => value === count)[1];
    item.activate(null);
    await until(() => !extension._busy && extension._state.physical_cores === count,
        'Radio selector did not apply the physical core count');
    const smt = extension._state.smt_enabled;
    extension._smt.toggle();
    await until(() => !extension._busy && extension._state.smt_enabled === !smt,
        'SMT toggle did not apply');
    assert(extension._state.physical_cores === count, 'SMT toggle changed physical core count');
    extension._smt.toggle();
    await until(() => !extension._busy && extension._state.smt_enabled === smt,
        'Second SMT toggle did not apply');
    assert(extension._state.physical_cores === count, 'Second SMT toggle changed core count');
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

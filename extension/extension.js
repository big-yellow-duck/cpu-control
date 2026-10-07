// SPDX-License-Identifier: Apache-2.0
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const BUS = 'io.github.big_yellow_duck.CpuControl1';
const PATH = '/io/github/big_yellow_duck/CpuControl1';

const SmtSwitchMenuItem = GObject.registerClass(
class CpuControlSmtSwitchMenuItem extends PopupMenu.PopupSwitchMenuItem {
    activate(_event) {
        // The inherited activation signal closes the menu. Toggle in place
        // for clicks, Enter and Space so the result stays visible.
        if (this.mapped && this.sensitive)
            this.toggle();
    }
});

export default class CpuControlExtension extends Extension {
    enable() {
        this._enabled = true;
        this._busy = false;
        this._refreshing = false;
        this._cancellable = new Gio.Cancellable();
        this._button = new PanelMenu.Button(0.0, 'CPU Control');
        this._label = new St.Label({text: 'CPU', y_align: Clutter.ActorAlign.CENTER});
        this._button.add_child(this._label);
        Main.panel.addToStatusArea(this.uuid, this._button);
        this._status = new PopupMenu.PopupMenuItem('Connecting…', {reactive: false});
        this._button.menu.addMenuItem(this._status);
        this._button.menu.connect('open-state-changed', (_menu, open) => {
            if (open)
                this._refresh();
        });
        this._signal = Gio.DBus.system.signal_subscribe(BUS, BUS, 'StateChanged', PATH,
            null, Gio.DBusSignalFlags.NONE, (_bus, _sender, _path, _iface, _signal, params) => {
                if (!this._busy) {
                    try {
                        this._render(JSON.parse(params.deepUnpack()[0]));
                    } catch (error) {
                        this._showError(error);
                    }
                }
            });
        this._poll = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this._refresh();
    }

    _call(method, parameters = null) {
        return new Promise((resolve, reject) => {
            Gio.DBus.system.call(BUS, PATH, BUS, method, parameters,
                new GLib.VariantType('(s)'), Gio.DBusCallFlags.NONE,
                method === 'GetState' ? 5000 : 75000, this._cancellable, (bus, result) => {
                    try {
                        resolve(JSON.parse(bus.call_finish(result).deepUnpack()[0]));
                    } catch (error) {
                        reject(error);
                    }
                });
        });
    }

    async _refresh() {
        if (!this._enabled || this._busy || this._refreshing)
            return;
        this._refreshing = true;
        try {
            const state = await this._call('GetState');
            if (this._enabled && !this._busy)
                this._render(state);
        } catch (error) {
            if (this._enabled && !this._busy)
                this._showError(error);
        } finally {
            this._refreshing = false;
        }
    }

    _render(state) {
        if (!this._enabled)
            return;
        this._state = state;
        const topology = JSON.stringify([state.ready, state.choices, state.total_cores, state.smt_supported]);
        if (this._topology !== topology) {
            this._topology = topology;
            this._button.menu.removeAll();
            this._heading = new PopupMenu.PopupMenuItem('CPU Cores', {reactive: false});
            this._button.menu.addMenuItem(this._heading);
            this._counts = [];
            if (state.ready) {
                for (const count of state.choices) {
                    const item = new PopupMenu.PopupMenuItem(`${count}`);
                    item.connect('activate', () => this._change('SetConfiguration',
                        new GLib.Variant('(ub)', [count, this._state.smt_enabled])));
                    this._button.menu.addMenuItem(item);
                    this._counts.push([count, item]);
                }
            } else {
                const detect = this._button.menu.addAction('Detect CPU topology…', () => this._change('Discover'));
                this._counts.push([null, detect]);
            }
            this._all = this._button.menu.addAction('All cores', () => this._change('RestoreAll'));
            this._button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            this._smt = new SmtSwitchMenuItem('SMT', false);
            this._smt.connect('toggled', (_item, enabled) => {
                if (!this._busy && !this._updating && this._state.ready)
                    this._change('SetConfiguration', new GLib.Variant('(ub)', [this._state.physical_cores, enabled]));
            });
            this._button.menu.addMenuItem(this._smt);
            this._status = new PopupMenu.PopupMenuItem('', {reactive: false});
            this._status.add_style_class_name('cpu-control-status');
            this._button.menu.addMenuItem(this._status);
        }
        this._label.text = state.ready ? `CPU ${state.physical_cores}` : 'CPU';
        this._heading.label.text = state.ready ? `CPU Cores · ${state.physical_cores} / ${state.total_cores}` : 'CPU Cores';
        for (const [count, item] of this._counts) {
            item.setOrnament(count === state.physical_cores ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NO_DOT);
            item.sensitive = !this._busy;
        }
        this._all.setOrnament(state.ready && state.physical_cores === state.total_cores
            ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NO_DOT);
        this._all.sensitive = !this._busy;
        this._updating = true;
        try {
            this._smt.setToggleState(state.smt_enabled);
        } finally {
            this._updating = false;
        }
        this._smt.sensitive = !this._busy && state.ready && state.smt_supported && state.smt_available;
        this._status.label.text = this._busy ? 'Applying…' : state.error ||
            (state.ready ? `${state.online_cpus.length} threads online${state.smt_mixed ? ' · SMT mixed' : ''}`
                : 'Detect topology to select cores');
    }

    async _change(method, parameters = null) {
        if (this._busy || !this._enabled)
            return;
        this._busy = true;
        if (this._state)
            this._render(this._state);
        let failure = null;
        try {
            const state = await this._call(method, parameters);
            if (this._enabled)
                this._state = state;
        } catch (error) {
            failure = error;
        } finally {
            this._busy = false;
            if (this._enabled) {
                if (this._state)
                    this._render(this._state);
                await this._refresh();
                if (failure)
                    this._showError(failure, true);
            }
        }
    }

    _showError(error, notify = false) {
        if (!this._enabled)
            return;
        const message = error.message.replace(/^GDBus\.Error:[^:]+:\s*/, '');
        this._status.label.text = `CPU Control: ${message}`;
        if (notify)
            Main.notify('CPU Control', message);
    }

    disable() {
        this._enabled = false;
        this._cancellable?.cancel();
        if (this._poll)
            GLib.Source.remove(this._poll);
        if (this._signal)
            Gio.DBus.system.signal_unsubscribe(this._signal);
        this._button?.destroy();
        this._button = null;
        this._cancellable = null;
        this._poll = 0;
        this._signal = 0;
        this._state = null;
        this._topology = null;
    }
}

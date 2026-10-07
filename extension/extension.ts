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

import {parseCpuState, type CpuState} from './cpuState.js';

type ChangeRequest =
    | [method: 'SetConfiguration', parameters: GLib.Variant<'(ub)'>]
    | [method: 'RestoreAll' | 'Discover', parameters?: null];
type CpuRequest = ChangeRequest | [method: 'GetState', parameters?: null];

const BUS = 'io.github.big_yellow_duck.CpuControl1';
const PATH = '/io/github/big_yellow_duck/CpuControl1';

const SmtSwitchMenuItem = GObject.registerClass(
class CpuControlSmtSwitchMenuItem extends PopupMenu.PopupSwitchMenuItem {
    activate(_event: Clutter.Event | null): void {
        // The inherited activation signal closes the menu. Toggle in place
        // for clicks, Enter and Space so the result stays visible.
        if (this.mapped && this.sensitive)
            this.toggle();
    }
});

export default class CpuControlExtension extends Extension {
    private declare _enabled: boolean;
    private declare _busy: boolean;
    private declare _refreshing: boolean;
    private declare _updating: boolean;
    private declare _cancellable: Gio.Cancellable | null;
    private declare _button: PanelMenu.Button | null;
    private declare _menu: PopupMenu.PopupMenu;
    private declare _label: St.Label;
    private declare _status: PopupMenu.PopupMenuItem;
    private declare _heading: PopupMenu.PopupMenuItem;
    private declare _counts: Array<[number | null, PopupMenu.PopupBaseMenuItem]>;
    private declare _all: PopupMenu.PopupBaseMenuItem;
    private declare _smt: InstanceType<typeof SmtSwitchMenuItem>;
    private declare _signal: number;
    private declare _poll: number;
    private declare _state: CpuState | null;
    private declare _topology: string | null;

    enable(): void {
        this._enabled = true;
        this._busy = false;
        this._refreshing = false;
        this._cancellable = new Gio.Cancellable();
        this._button = new PanelMenu.Button(0.0, 'CPU Control');
        // Button creates a real popup menu when dontCreateMenu is omitted.
        if (!(this._button.menu instanceof PopupMenu.PopupMenu))
            throw new Error('CPU Control requires a popup menu');
        this._menu = this._button.menu;
        this._label = new St.Label({text: 'CPU', y_align: Clutter.ActorAlign.CENTER});
        this._button.add_child(this._label);
        Main.panel.addToStatusArea(this.uuid, this._button);
        this._status = new PopupMenu.PopupMenuItem('Connecting…', {reactive: false});
        this._menu.addMenuItem(this._status);
        this._menu.connect('open-state-changed', (_menu: PopupMenu.PopupMenu, open: boolean) => {
            if (open)
                this._refresh();
        });
        this._signal = Gio.DBus.system.signal_subscribe(BUS, BUS, 'StateChanged', PATH,
            null, Gio.DBusSignalFlags.NONE, (_bus, _sender, _path, _iface, _signal, params) => {
                if (!this._busy) {
                    try {
                        this._render(parseCpuState(params.deepUnpack<[string]>()[0]));
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

    private _call(...[method, parameters = null]: CpuRequest): Promise<CpuState> {
        return new Promise<CpuState>((resolve, reject) => {
            Gio.DBus.system.call(BUS, PATH, BUS, method, parameters,
                new GLib.VariantType('(s)'), Gio.DBusCallFlags.NONE,
                method === 'GetState' ? 5000 : 75000, this._cancellable, (bus, result) => {
                    try {
                        if (!bus)
                            throw new Error('CPU Control D-Bus connection is unavailable');
                        resolve(parseCpuState(bus.call_finish(result).deepUnpack<[string]>()[0]));
                    } catch (error) {
                        reject(error);
                    }
                });
        });
    }

    private async _refresh(): Promise<void> {
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

    private _render(state: CpuState): void {
        if (!this._enabled)
            return;
        this._state = state;
        const topology = JSON.stringify([state.ready, state.choices, state.total_cores, state.smt_supported]);
        if (this._topology !== topology) {
            this._topology = topology;
            this._menu.removeAll();
            this._heading = new PopupMenu.PopupMenuItem('CPU Cores', {reactive: false});
            this._menu.addMenuItem(this._heading);
            this._counts = [];
            if (state.ready) {
                for (const count of state.choices) {
                    const item = new PopupMenu.PopupMenuItem(`${count}`);
                    item.connect('activate', () => this._change('SetConfiguration',
                        new GLib.Variant('(ub)', [count, this._state?.smt_enabled ?? false])));
                    this._menu.addMenuItem(item);
                    this._counts.push([count, item]);
                }
            } else {
                const detect = this._menu.addAction('Detect CPU topology…', () => this._change('Discover'));
                this._counts.push([null, detect]);
            }
            this._all = this._menu.addAction('All cores', () => this._change('RestoreAll'));
            this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            this._smt = new SmtSwitchMenuItem('SMT', false);
            this._smt.connect('toggled', (_item: PopupMenu.PopupSwitchMenuItem, enabled: boolean) => {
                if (!this._busy && !this._updating && this._state?.ready)
                    this._change('SetConfiguration', new GLib.Variant('(ub)', [this._state.physical_cores, enabled]));
            });
            this._menu.addMenuItem(this._smt);
            this._status = new PopupMenu.PopupMenuItem('', {reactive: false});
            this._status.add_style_class_name('cpu-control-status');
            this._menu.addMenuItem(this._status);
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

    private async _change(...request: ChangeRequest): Promise<void> {
        if (this._busy || !this._enabled)
            return;
        this._busy = true;
        if (this._state)
            this._render(this._state);
        let failure: unknown = null;
        try {
            const state = await this._call(...request);
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

    private _showError(error: unknown, notify = false): void {
        if (!this._enabled)
            return;
        const message = (error instanceof Error ? error.message : String(error)).replace(/^GDBus\.Error:[^:]+:\s*/, '');
        this._status.label.text = `CPU Control: ${message}`;
        if (notify)
            Main.notify('CPU Control', message);
    }

    disable(): void {
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

// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {parseCpuState} from '../dist/cpuState.js';

const state = {
    ready: true, physical_cores: 8, total_cores: 8,
    online_cpus: [0, 1, 2, 3, 4, 5, 6, 7], total_threads: 16,
    smt_enabled: false, smt_mixed: false, smt_supported: true,
    smt_available: true, smt_control: 'off', pinned_cpus: [0],
    choices: [1, 2, 4, 6], error: '',
};

test('accepts helper state, including undiscovered topology and helper errors', () => {
    assert.deepEqual(parseCpuState(JSON.stringify(state)), state);
    const notReady = {...state, ready: false, total_cores: 0, physical_cores: 0,
        choices: [], smt_supported: false, error: 'Detect topology first'};
    assert.deepEqual(parseCpuState(JSON.stringify(notReady)), notReady);
});

test('rejects invalid JSON and non-object payloads', () => {
    for (const json of ['{', 'null', '[]', 'false', '42'])
        assert.throws(() => parseCpuState(json));
});

test('rejects missing fields and incorrect field types before rendering', () => {
    for (const key of Object.keys(state)) {
        const missing = {...state};
        delete missing[key];
        assert.throws(() => parseCpuState(JSON.stringify(missing)), /Invalid CPU Control state/);
        assert.throws(() => parseCpuState(JSON.stringify({...state, [key]: null})), /Invalid CPU Control state/);
    }
    for (const [key, value] of [
        ['ready', 1], ['physical_cores', -1], ['total_cores', 1.5],
        ['online_cpus', ['0']], ['choices', [-1]], ['pinned_cpus', [null]],
    ])
        assert.throws(() => parseCpuState(JSON.stringify({...state, [key]: value})), /Invalid CPU Control state/);
});

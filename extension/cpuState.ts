// SPDX-License-Identifier: Apache-2.0
export interface CpuState {
    ready: boolean;
    physical_cores: number;
    total_cores: number;
    online_cpus: number[];
    total_threads: number;
    smt_enabled: boolean;
    smt_mixed: boolean;
    smt_supported: boolean;
    smt_available: boolean;
    smt_control: string;
    pinned_cpus: number[];
    choices: number[];
    error: string;
}

// D-Bus carries JSON, so check the boundary before trusting its TypeScript type.
export function parseCpuState(json: string): CpuState {
    const value: unknown = JSON.parse(json);
    if (typeof value !== 'object' || value === null || Array.isArray(value))
        throw new Error('Invalid CPU Control state: expected an object');
    const state = value as Record<string, unknown>;
    for (const key of ['ready', 'smt_enabled', 'smt_mixed', 'smt_supported', 'smt_available']) {
        if (typeof state[key] !== 'boolean')
            throw new Error(`Invalid CPU Control state: ${key}`);
    }
    for (const key of ['physical_cores', 'total_cores', 'total_threads']) {
        if (typeof state[key] !== 'number' || !Number.isSafeInteger(state[key]) || state[key] < 0)
            throw new Error(`Invalid CPU Control state: ${key}`);
    }
    for (const key of ['online_cpus', 'pinned_cpus', 'choices']) {
        const values = state[key];
        if (!Array.isArray(values) || !values.every((item: unknown) =>
            typeof item === 'number' && Number.isSafeInteger(item) && item >= 0))
            throw new Error(`Invalid CPU Control state: ${key}`);
    }
    if (typeof state.smt_control !== 'string' || typeof state.error !== 'string')
        throw new Error('Invalid CPU Control state: expected status strings');
    return state as unknown as CpuState;
}

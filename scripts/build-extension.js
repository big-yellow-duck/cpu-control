// SPDX-License-Identifier: Apache-2.0
import {copyFileSync} from 'node:fs';

for (const name of ['metadata.json', 'stylesheet.css'])
    copyFileSync(new URL(`../extension/${name}`, import.meta.url), new URL(`../dist/${name}`, import.meta.url));
copyFileSync(new URL('../LICENSE', import.meta.url), new URL('../dist/LICENSE', import.meta.url));

#!/usr/bin/env node
// node deploy/rollback.js [--to <version>] [--force-restore]   see RUNBOOK.md
import { parseArgs } from 'node:util';
import { rollback, layout } from './lib.js';

const { values } = parseArgs({ options: { to: { type: 'string' }, 'force-restore': { type: 'boolean' }, reason: { type: 'string' } } });
try {
  const r = await rollback({ L: layout(), to: values.to, forceRestore: values['force-restore'], reason: values.reason ?? 'manual' });
  console.log(`[rollback] ${r.ok ? 'OK' : 'SMOKE FAILED'}: ${r.from} -> ${r.to} in ${(r.ms / 1000).toFixed(1)} s`);
  process.exit(r.ok ? 0 : 1);
} catch (e) {
  console.error(`[rollback] FAILED: ${e.message}`);
  process.exit(1);
}

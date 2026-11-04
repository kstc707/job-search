#!/usr/bin/env node
// node deploy/deploy.js <version>   see RUNBOOK.md
import { deploy, layout, ensureEnv } from './lib.js';

const version = process.argv[2];
if (!version) {
  console.error('usage: node deploy/deploy.js <version>');
  process.exit(64);
}
const L = layout();
ensureEnv(L);
try {
  const r = await deploy(version, { L });
  process.exit(r.ok ? 0 : 1);
} catch (e) {
  console.error(`[deploy] FAILED: ${e.message}`);
  process.exit(1);
}

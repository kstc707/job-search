#!/usr/bin/env node
// Drill: a bad 1.1.0 build (technology fee changed from 4% to 5% by mistake) is deployed over 1.0.0.
// Smoke check 12 catches the fee change and deploy.js rolls back on its own.
// Writes results/failed-upgrade-drill.md. Does not modify the checkout (config is patched only in the artifact).
import { readFileSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { PROJECT, layout, ensureEnv, packageRelease, deploy, stopApp, readCurrent } from './lib.js';
import { startMock } from '../mocks/downstream.js';

const L = layout(join(PROJECT, '.deploy', 'drill-failed-upgrade'));
rmSync(L.dir, { recursive: true, force: true });
mkdirSync(L.dir, { recursive: true });
const mock = await startMock({ webhookSecret: 'drill' });
ensureEnv(L, { port: 3917, mockUrl: mock.url, webhookSecret: 'drill' });
const lines = [];
const log = (l) => lines.push(l);
let r;
try {
  packageRelease('1.0.0', L);
  packageRelease('1.1.0', L);
  const feesFile = join(L.releases, '1.1.0', 'config', 'fees.json');
  writeFileSync(feesFile, readFileSync(feesFile, 'utf8').replace('"technologyFeePercent": 4', '"technologyFeePercent": 5'));
  await deploy('1.0.0', { L, log });
  r = await deploy('1.1.0', { L, log });
} finally {
  await stopApp(L);
  await mock.close();
}
const live = readCurrent(L);
const ok = r.ok === false && r.rolledBack?.ok === true && live.version === '1.0.0';
const failed = r.smoke.results.filter((x) => x.status === 'fail');
const md = [
  '# Drill: failed upgrade with automatic rollback',
  '',
  `Generated ${new Date().toISOString()} by \`node deploy/drill-failed-upgrade.js\`.`,
  '',
  '- Bad build: 1.1.0 artifact with the technology fee changed from 4% to 5%.',
  `- Smoke on 1.1.0: ${r.smoke.passed} passed, ${r.smoke.failed} failed, ${r.smoke.skipped} skipped. Failed: ${failed.map((f) => `#${f.n} ${f.name} (${f.detail})`).join('; ')}.`,
  `- Automatic rollback to ${r.rolledBack.to}: ${r.rolledBack.ok ? 'smoke green' : 'SMOKE FAILED'} in ${(r.rolledBack.ms / 1000).toFixed(2)} s; data path: ${r.rolledBack.dataPath}.`,
  `- Live release afterwards: ${live.version}. Result: **${ok ? 'PASS' : 'FAIL'}**.`,
  '',
  '```',
  ...lines.filter((l) => /^\[|FAIL/.test(l.trim())).map((l) => l.replace(PROJECT, '.')),
  '```',
  '',
].join('\n');
mkdirSync(join(PROJECT, 'results'), { recursive: true });
writeFileSync(join(PROJECT, 'results', 'failed-upgrade-drill.md'), md);
console.log(md);
process.exit(ok ? 0 : 1);

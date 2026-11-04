#!/usr/bin/env node
// Deployment + rollback rehearsal, run N times from a clean deploy directory each time:
//   1. package 1.0.0 and 1.1.0
//   2. deploy 1.0.0 (fresh install) and seed 5 permits in different states
//   3. upgrade to 1.1.0 (migration 002 up) + 20 smoke tests
//   4. create a permit on 1.1.0 (SMS channel, flood-zone parcel data) that must survive the rollback
//   5. ROLL BACK to 1.0.0, timed from the first rollback step to the 20th smoke test passing
//   6. verify the seeded and post-upgrade permits on 1.0.0
// Writes results/rehearsals.json and results/rehearsals.md.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import os from 'node:os';
import { PROJECT, layout, ensureEnv, packageRelease, deploy, rollback, stopApp } from './lib.js';
import { seed } from './seed.js';
import { startMock } from '../mocks/downstream.js';

const { values } = parseArgs({ options: { runs: { type: 'string', default: '3' }, verbose: { type: 'boolean' } } });
const RUNS = Number(values.runs);
const TEN_MINUTES_MS = 10 * 60 * 1000;

const freePort = () =>
  new Promise((resolve) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });

async function rehearse(n) {
  const L = layout(join(PROJECT, '.deploy', 'rehearsals', `run-${n}`));
  rmSync(L.dir, { recursive: true, force: true });
  mkdirSync(L.dir, { recursive: true });
  const secret = `rehearsal-${n}-${Date.now()}`;
  const mock = await startMock({ webhookSecret: secret });
  const port = await freePort();
  const env = ensureEnv(L, { port, mockUrl: mock.url, webhookSecret: secret });
  const lines = [];
  const log = (l) => {
    lines.push(l);
    if (values.verbose) console.log(l);
  };
  const api = async (method, path, body) => (await fetch(env.PUBLIC_URL + path, { method, headers: { 'content-type': 'application/json' }, body: body && JSON.stringify(body) })).json();
  const run = { run: n, startedAt: new Date().toISOString() };
  try {
    packageRelease('1.0.0', L);
    packageRelease('1.1.0', L);

    const install = await deploy('1.0.0', { L, log });
    run.install = { ok: install.ok, ms: install.ms, smoke: pick(install.smoke) };
    if (!install.ok) throw new Error('install of 1.0.0 failed smoke');
    run.seeded = (await seed(env.PUBLIC_URL, L.seed)).length;

    const upgrade = await deploy('1.1.0', { L, log, autoRollback: false });
    run.upgrade = { ok: upgrade.ok, ms: upgrade.ms, smoke: pick(upgrade.smoke) };
    if (!upgrade.ok) throw new Error('upgrade to 1.1.0 failed smoke');

    const post = await api('POST', '/permits', { permitType: 'building', applicant: { name: 'Post Upgrade', email: 'post@example.org', phone: '+15550001111', notifyChannel: 'sms' }, parcelId: 'P-1004', description: 'Created on 1.1.0', valuation: 50000 });
    if (post.applicant?.notifyChannel !== 'sms') throw new Error('v1.1 feature not live after upgrade');

    const rb = await rollback({ L, log, reason: 'rehearsal' });
    run.rollback = { ok: rb.ok, ms: rb.ms, dataPath: rb.dataPath, smoke: pick(rb.smoke) };

    const after = await api('GET', `/permits/${post.id}`);
    const version = await api('GET', '/version');
    run.checks = {
      runningVersionAfterRollback: version.version,
      postUpgradePermitPreserved: after.id === post.id && after.applicant.name === 'Post Upgrade' && after.applicant.notifyChannel === undefined,
      seededPermitsVerifiedBySmoke: rb.smoke.results.filter((r) => [5, 6, 7].includes(r.n)).every((r) => r.status === 'pass'),
    };
    run.ok = install.ok && upgrade.ok && rb.ok && version.version === '1.0.0' && run.checks.postUpgradePermitPreserved && run.checks.seededPermitsVerifiedBySmoke;
    run.withinTenMinutes = rb.ms < TEN_MINUTES_MS;
  } catch (e) {
    run.ok = false;
    run.error = e.message;
  } finally {
    await stopApp(L);
    await mock.close();
  }
  run.log = lines;
  return run;
}

const pick = (s) => ({ total: s.total, passed: s.passed, failed: s.failed, skipped: s.skipped });

const runs = [];
for (let i = 1; i <= RUNS; i++) {
  const r = await rehearse(i);
  runs.push(r);
  console.log(`run ${i}: ${r.ok ? 'PASS' : 'FAIL'}` + (r.rollback ? ` | rollback ${(r.rollback.ms / 1000).toFixed(2)} s, smoke ${r.rollback.smoke.passed}/${r.rollback.smoke.total}, ${r.rollback.dataPath}` : '') + (r.error ? ` | ${r.error}` : ''));
}

const rb = runs.filter((r) => r.rollback).map((r) => r.rollback.ms).sort((a, b) => a - b);
const summary = {
  runs: runs.length,
  allPassed: runs.every((r) => r.ok),
  rollbackMs: { min: rb[0] ?? null, median: rb[Math.floor(rb.length / 2)] ?? null, max: rb.at(-1) ?? null },
  allWithinTenMinutes: runs.every((r) => r.withinTenMinutes),
};
const out = {
  generatedAt: new Date().toISOString(),
  environment: { node: process.version, platform: `${os.platform()} ${os.release()}`, cpus: os.cpus().length, cpuModel: os.cpus()[0]?.model ?? null },
  summary,
  runs: runs.map(({ log, ...r }) => r),
};
mkdirSync(join(PROJECT, 'results'), { recursive: true });
writeFileSync(join(PROJECT, 'results', 'rehearsals.json'), JSON.stringify(out, null, 2) + '\n');

const s = (x) => `${x.passed}/${x.total} pass, ${x.skipped} skip, ${x.failed} fail`;
const md = [
  '# Deployment and rollback rehearsals',
  '',
  `Generated ${out.generatedAt} by \`node deploy/rehearse.js --runs ${RUNS}\` on ${out.environment.platform}, Node ${out.environment.node}, ${out.environment.cpus} CPU(s).`,
  'Each run starts from an empty deploy directory. Rollback time is measured from the first rollback step (stop 1.1.0) to the 20th smoke test passing on 1.0.0.',
  '',
  '| Run | Install 1.0.0 | Upgrade to 1.1.0 (smoke) | Rollback to 1.0.0 (smoke) | Rollback time | Data path | Post-upgrade permit kept | Result |',
  '|---|---|---|---|---|---|---|---|',
  ...runs.map((r) =>
    r.rollback
      ? `| ${r.run} | ${(r.install.ms / 1000).toFixed(2)} s (${s(r.install.smoke)}) | ${(r.upgrade.ms / 1000).toFixed(2)} s (${s(r.upgrade.smoke)}) | ${s(r.rollback.smoke)} | **${(r.rollback.ms / 1000).toFixed(2)} s** | ${r.rollback.dataPath} | ${r.checks.postUpgradePermitPreserved ? 'yes' : 'no'} | ${r.ok ? 'PASS' : 'FAIL'} |`
      : `| ${r.run} | - | - | - | - | - | - | FAIL: ${r.error} |`
  ),
  '',
  `All runs passed: **${summary.allPassed ? 'yes' : 'no'}**. Rollback time min / median / max: ${[summary.rollbackMs.min, summary.rollbackMs.median, summary.rollbackMs.max].map((v) => (v == null ? '-' : `${(v / 1000).toFixed(2)} s`)).join(' / ')}. All under 10 minutes: **${summary.allWithinTenMinutes ? 'yes' : 'no'}**.`,
  '',
  'The install run skips smoke checks 5-7 (they compare against permits seeded before the deploy, and a first install has none).',
  'These are local single-machine timings with mock downstream services; a real platform adds artifact transfer, approvals and slower dependencies (see README limitations).',
  '',
].join('\n');
writeFileSync(join(PROJECT, 'results', 'rehearsals.md'), md);
console.log(`\n${summary.allPassed ? 'ALL PASSED' : 'FAILURES'}; rollback ms ${JSON.stringify(summary.rollbackMs)}; results/rehearsals.md written`);
process.exit(summary.allPassed ? 0 : 1);

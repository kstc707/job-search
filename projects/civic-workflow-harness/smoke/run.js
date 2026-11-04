#!/usr/bin/env node
// 20 upgrade smoke tests, run against a LIVE deployment after every deploy and rollback.
//   BASE_URL=http://127.0.0.1:3000 EXPECT_VERSION=1.1.0 WEBHOOK_SECRET=... SEED_FILE=.deploy/seed.json node smoke/run.js
// Smoke permits are tagged "smoke" so they can be filtered out of reports.
// Checks 5-7 compare against a seed file of records that existed before the deploy; without one they
// are reported as skipped (only on a first install, when no earlier data exists).
import { readFileSync, existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { sign } from '../src/lib/signature.js';

const PDF = Buffer.from('%PDF-1.4 smoke').toString('base64');
const SMOKE_PERMIT = {
  permitType: 'building',
  applicant: { name: 'Smoke Test', email: 'smoke@example.org' },
  parcelId: 'P-1001',
  description: 'Post-deploy smoke test',
  valuation: 100000,
  tags: ['smoke'],
};
const EXPECTED_SMOKE_FEE_CENTS = 93600; // building, $100,000 valuation, per config/fees.json

class Skip extends Error {}

export async function runSmoke({ baseUrl, expectVersion, webhookSecret, seedFile, log = console.log, pollMs = 5000 }) {
  const call = async (method, path, body, headers = {}) => {
    const res = await fetch(baseUrl + path, {
      method,
      headers: { 'content-type': 'application/json', ...headers },
      body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });
    const text = await res.text();
    let json = null;
    try { json = text ? JSON.parse(text) : null; } catch { /* keep text */ }
    return { status: res.status, body: json, text };
  };
  const expect = (cond, msg) => { if (!cond) throw new Error(msg); };
  const seed = seedFile && existsSync(seedFile) ? JSON.parse(readFileSync(seedFile, 'utf8')) : null;
  const needSeed = () => { if (!seed) throw new Skip('no seed file (first install)'); };
  const c = {};
  const waitStatus = async (id, status) => {
    const end = Date.now() + pollMs;
    for (;;) {
      const r = await call('GET', `/permits/${id}`);
      if (r.body?.status === status) return r.body;
      if (Date.now() > end) throw new Error(`permit ${id} did not reach ${status} (is ${r.body?.status})`);
      await new Promise((res) => setTimeout(res, 50));
    }
  };

  const checks = [
    ['health endpoint answers ok', async () => {
      const r = await call('GET', '/health');
      expect(r.status === 200 && r.body.status === 'ok', `health ${r.status} ${r.text}`);
      c.health = r.body;
    }],
    ['running version is the release just deployed', async () => {
      const r = await call('GET', '/version');
      c.version = r.body;
      if (!expectVersion) throw new Skip('EXPECT_VERSION not set');
      expect(r.body.version === expectVersion, `running ${r.body.version}, expected ${expectVersion}`);
    }],
    ['data store schema matches the release schema', async () => {
      expect(c.health.schemaVersion === c.health.storeSchemaVersion, `release schema ${c.health.schemaVersion}, store ${c.health.storeSchemaVersion}`);
    }],
    ['every downstream dependency is reachable', async () => {
      const r = await call('GET', '/health?deep=1');
      const down = Object.entries(r.body.dependencies).filter(([, v]) => v !== 'up');
      expect(down.length === 0, `down: ${down.map(([k, v]) => `${k}=${v}`).join(', ')}`);
    }],
    ['pre-existing permits are still readable', async () => {
      needSeed();
      for (const p of seed.permits) {
        const r = await call('GET', `/permits/${p.id}`);
        expect(r.status === 200, `${p.id} -> HTTP ${r.status}`);
      }
    }],
    ['pre-existing permit statuses are unchanged', async () => {
      needSeed();
      for (const p of seed.permits) {
        const r = await call('GET', `/permits/${p.id}`);
        expect(r.body.status === p.status, `${p.id} is ${r.body.status}, was ${p.status}`);
      }
    }],
    ['pre-existing permit data is intact (applicant, valuation, invoice)', async () => {
      needSeed();
      for (const p of seed.permits) {
        const r = (await call('GET', `/permits/${p.id}`)).body;
        expect(r.applicant.name === p.applicantName && r.valuation === p.valuation && (r.invoice?.totalCents ?? null) === p.invoiceTotalCents, `${p.id} fields changed`);
      }
    }],
    ['invalid permit is rejected with 400', async () => {
      const r = await call('POST', '/permits', { permitType: 'building', applicant: { email: 'nope' } });
      expect(r.status === 400 && r.body.error.code === 'invalid_fields', `got ${r.status}`);
    }],
    ['create a draft permit', async () => {
      const r = await call('POST', '/permits', SMOKE_PERMIT);
      expect(r.status === 201 && r.body.status === 'draft', `create ${r.status} ${r.text}`);
      c.id = r.body.id;
    }],
    ['upload the required documents', async () => {
      for (const type of ['site_plan', 'construction_drawings']) {
        const r = await call('POST', `/permits/${c.id}/documents`, { type, filename: `${type}.pdf`, contentBase64: PDF });
        expect(r.status === 201, `${type}: ${r.status} ${r.text}`);
      }
    }],
    ['submit with missing fields is refused with 422', async () => {
      const d = await call('POST', '/permits', { permitType: 'building', applicant: { email: 'smoke@example.org' }, tags: ['smoke'] });
      const r = await call('POST', `/permits/${d.body.id}/submit`);
      expect(r.status === 422 && r.body.error.code === 'missing_fields', `got ${r.status}`);
    }],
    ['submit assesses fees from the fee schedule', async () => {
      const r = await call('POST', `/permits/${c.id}/submit`);
      expect(r.status === 200 && r.body.status === 'fees_assessed', `submit ${r.status} ${r.text}`);
      expect(r.body.invoice.totalCents === EXPECTED_SMOKE_FEE_CENTS, `fee ${r.body.invoice.totalCents}, expected ${EXPECTED_SMOKE_FEE_CENTS}`);
    }],
    ['payment request is accepted', async () => {
      const r = await call('POST', `/permits/${c.id}/payments`);
      expect(r.status === 202 && r.body.permit.payment.status === 'pending', `pay ${r.status} ${r.text}`);
    }],
    ['signed payment callback marks the permit paid', async () => {
      c.paid = await waitStatus(c.id, 'paid');
    }],
    ['a replayed callback is a no-op', async () => {
      if (!webhookSecret) throw new Skip('WEBHOOK_SECRET not set');
      const pay = c.paid.payment;
      const raw = JSON.stringify({ id: pay.appliedEventIds.at(-1), type: 'charge.succeeded', sequence: pay.lastSequence, chargeId: pay.chargeId, permitId: c.id, idempotencyKey: pay.idempotencyKey, amountCents: pay.amountCents });
      const r = await call('POST', '/callbacks/payment', raw, { 'x-signature': sign(webhookSecret, raw) });
      expect(r.status === 200 && r.body.duplicate === true, `replay ${r.status} ${r.text}`);
      const after = (await call('GET', `/permits/${c.id}`)).body;
      expect(after.history.length === c.paid.history.length, 'history changed on replay');
    }],
    ['an unsigned callback is rejected with 401', async () => {
      const r = await call('POST', '/callbacks/payment', { id: 'evt_smoke_forged', type: 'charge.succeeded', sequence: 9, idempotencyKey: 'x' });
      expect(r.status === 401, `got ${r.status}`);
    }],
    ['review, approve and issue', async () => {
      for (const action of ['start_review', 'approve', 'issue']) {
        const r = await call('POST', `/permits/${c.id}/transitions`, { action });
        expect(r.status === 200, `${action}: ${r.status} ${r.text}`);
      }
      await waitStatus(c.id, 'issued');
    }],
    ['a passed final inspection closes the permit', async () => {
      const r = await call('POST', `/permits/${c.id}/inspections`, { type: 'final', result: 'pass', inspector: 'Smoke Inspector' });
      expect(r.status === 201 && r.body.permit.status === 'finaled', `inspection ${r.status} ${r.text}`);
    }],
    ['release-specific fields match the running schema', async () => {
      const p = (await call('GET', `/permits/${c.id}`)).body;
      if (c.version.schemaVersion >= 2) {
        expect(p.floodZone === 'X' && p.applicant.notifyChannel === 'email', `v1.1 fields missing: floodZone=${p.floodZone} notifyChannel=${p.applicant.notifyChannel}`);
      } else {
        expect(!('floodZone' in p) && p.applicant.notifyChannel === undefined, 'v1.1 fields present on a schema-1 release');
      }
    }],
    ['notifications are delivered and nothing is dead-lettered', async () => {
      await call('POST', '/admin/outbox/flush');
      const r = (await call('GET', `/admin/outbox?permitId=${c.id}`)).body;
      expect(r.dead === 0, `${r.dead} dead-lettered notifications`);
      const notSent = r.entries.filter((e) => e.status !== 'sent');
      expect(r.entries.length >= 5 && notSent.length === 0, `${notSent.length} of ${r.entries.length} smoke notifications not sent`);
    }],
  ];

  const results = [];
  for (const [i, [name, fn]] of checks.entries()) {
    const t0 = Date.now();
    let status = 'pass';
    let detail = '';
    try {
      await fn();
    } catch (e) {
      status = e instanceof Skip ? 'skip' : 'fail';
      detail = e.message;
    }
    results.push({ n: i + 1, name, status, ms: Date.now() - t0, detail });
    log(`${status.toUpperCase().padEnd(4)} ${String(i + 1).padStart(2)}. ${name}${detail ? ` - ${detail}` : ''}`);
  }
  const tally = (st) => results.filter((r) => r.status === st).length;
  return { total: results.length, passed: tally('pass'), failed: tally('fail'), skipped: tally('skip'), results };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const r = await runSmoke({
    baseUrl: process.env.BASE_URL ?? 'http://127.0.0.1:3000',
    expectVersion: process.env.EXPECT_VERSION,
    webhookSecret: process.env.WEBHOOK_SECRET ?? 'dev-webhook-secret',
    seedFile: process.env.SEED_FILE,
  });
  console.log(`\nsmoke: ${r.passed} passed, ${r.failed} failed, ${r.skipped} skipped (of ${r.total})`);
  process.exit(r.failed ? 1 : 0);
}

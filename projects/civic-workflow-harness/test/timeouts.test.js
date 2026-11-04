// Timeouts: hung and slow downstream services. Adapter timeout is 200 ms in these tests.
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { startStack, waitFor, PDF } from './helpers.js';

let s;
before(async () => { s = await startStack({ timeoutMs: 200, backoffMs: 10 }); });
after(() => s.close());
beforeEach(() => s.reset());

test('a hung GIS service fails submit with 504 within the retry budget and keeps the draft', async () => {
  const id = await s.createReady();
  await s.fault('gis', { hang: true });
  const t0 = Date.now();
  const r = await s.api('POST', `/permits/${id}/submit`);
  const elapsed = Date.now() - t0;
  assert.equal(r.status, 504);
  assert.equal(r.body.error.code, 'downstream_timeout');
  assert.equal(r.body.error.service, 'gis');
  assert.equal((await s.calls('gis')).length, 3, '1 try + 2 retries (GET is idempotent)');
  assert.ok(elapsed < 3 * 200 + 30 + 500, `bounded: took ${elapsed} ms`);
  assert.equal((await s.get(id)).status, 'draft');
});

test('one slow GIS response is retried and the submit succeeds', async () => {
  const id = await s.createReady();
  await s.fault('gis', { latencyMs: 600, count: 1 });
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 200);
  assert.equal(r.body.status, 'fees_assessed');
  assert.equal((await s.calls('gis')).length, 2);
});

test('a hung payment service answers 202 "unknown", opens reconciliation and is not retried', async () => {
  const id = await s.toFeesAssessed();
  await s.fault('payment', { hang: true });
  const r = await s.api('POST', `/permits/${id}/payments`);
  assert.equal(r.status, 202);
  assert.equal(r.body.permit.payment.status, 'unknown');
  assert.equal(r.body.permit.status, 'fees_assessed');
  assert.equal((await s.calls('payment')).length, 1, 'a timed-out charge is never blindly retried');
  const items = (await s.api('GET', '/admin/reconciliation')).body.items.filter((x) => x.permitId === id);
  assert.equal(items.length, 1);
  assert.equal(items[0].status, 'open');
  assert.equal(items[0].reason, 'charge_timeout');
  const again = await s.api('POST', `/permits/${id}/payments`);
  assert.equal(again.body.reused, true, 'a second click while unknown does not create another charge');
});

test('a charge that completes after the timeout is resolved by its late callback', async () => {
  const id = await s.toFeesAssessed();
  await s.fault('payment', { latencyMs: 400, count: 1 });
  const r = await s.api('POST', `/permits/${id}/payments`);
  assert.equal(r.body.permit.payment.status, 'unknown');
  const p = await waitFor(async () => { const x = await s.get(id); return x.status === 'paid' && x; });
  assert.match(p.payment.chargeId, /^ch_\d+$/, 'the late callback filled in the charge id');
  const item = (await s.api('GET', '/admin/reconciliation')).body.items.find((x) => x.permitId === id);
  assert.equal(item.status, 'closed');
  assert.match(item.resolution, /^resolved_by_callback/);
});

test('reconciliation clears a charge that was never created, and the applicant can pay again', async () => {
  const id = await s.toFeesAssessed();
  await s.fault('payment', { hang: true, count: 1 });
  await s.api('POST', `/permits/${id}/payments`);
  const rec = await s.api('POST', '/admin/reconcile');
  assert.equal(rec.body.stillOpen, 0);
  const item = (await s.api('GET', '/admin/reconciliation')).body.items.find((x) => x.permitId === id);
  assert.deepEqual([item.status, item.resolution], ['closed', 'not_created']);
  assert.equal((await s.get(id)).payment.status, 'not_created');
  await s.api('POST', `/permits/${id}/payments`);
  const p = await waitFor(async () => { const x = await s.get(id); return x.status === 'paid' && x; });
  assert.equal(p.payment.attempt, 2);
});

test('reconciliation finds a charge that succeeded without a callback and marks the permit paid', async () => {
  const id = await s.toFeesAssessed();
  await s.fault('payment', { latencyMs: 300, count: 1, suppressCallbacks: true });
  await s.api('POST', `/permits/${id}/payments`);
  await new Promise((r) => setTimeout(r, 400)); // provider finishes creating the charge
  const rec = await s.api('POST', '/admin/reconcile');
  assert.equal(rec.body.resolved, 1);
  const p = await s.get(id);
  assert.equal(p.status, 'paid');
  assert.equal(p.payment.status, 'succeeded');
});

test('a hung notification service does not block the workflow', async () => {
  const id = await s.createReady();
  await s.fault('notify', { hang: true });
  const t0 = Date.now();
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 200);
  assert.equal(r.body.status, 'fees_assessed');
  assert.ok(Date.now() - t0 < 200, 'submit returned before the notification timed out');
  await s.api('POST', '/admin/outbox/flush');
  const [entry] = (await s.api('GET', `/admin/outbox?permitId=${id}`)).body.entries;
  assert.equal(entry.status, 'pending');
  assert.match(entry.lastError, /downstream_timeout/);
});

test('a document upload timeout returns 504 and records nothing', async () => {
  const c = await s.api('POST', '/permits', { permitType: 'electrical', applicant: { email: 'e@example.org' } });
  await s.fault('documents', { hang: true });
  const r = await s.api('POST', `/permits/${c.body.id}/documents`, { type: 'load_calculation', filename: 'load.pdf', contentBase64: PDF });
  assert.equal(r.status, 504);
  assert.equal(r.body.error.service, 'documents');
  assert.equal((await s.calls('documents')).length, 1, 'non-idempotent upload is not retried');
  assert.equal((await s.get(c.body.id)).documents.length, 0);
});

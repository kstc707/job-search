// Failed downstream services: 5xx, 4xx, malformed bodies. Which failures block and which degrade.
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { startStack, waitFor, PDF } from './helpers.js';

let s;
before(async () => { s = await startStack({ timeoutMs: 200, backoffMs: 10 }); });
after(() => s.close());
beforeEach(() => s.reset());

test('GIS 503 is retried twice, then submit fails with 503 and a clear message', async () => {
  const id = await s.createReady();
  await s.fault('gis', { status: 503 });
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 503);
  assert.equal(r.body.error.code, 'downstream_unavailable');
  assert.match(r.body.error.message, /gis returned HTTP 503/);
  assert.equal((await s.calls('gis')).length, 3);
  assert.equal((await s.get(id)).status, 'draft');
});

test('an unknown parcel is a 422 for the applicant and is not retried', async () => {
  const id = await s.createReady({ parcelId: 'P-9999' });
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 422);
  assert.equal(r.body.error.code, 'unknown_parcel');
  assert.equal((await s.calls('gis')).length, 1);
});

test('a malformed GIS response is a 502, not a crash', async () => {
  const id = await s.createReady();
  await s.fault('gis', { malformed: true });
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 502);
  assert.equal(r.body.error.code, 'downstream_bad_response');
  assert.equal((await s.get(id)).status, 'draft');
});

test('zoning that does not allow the permit type blocks submit with 422', async () => {
  const id = await s.createReady({ parcelId: 'P-1005' });
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 422);
  assert.equal(r.body.error.code, 'zoning_not_permitted');
  assert.equal(r.body.error.details.zoning, 'AG');
});

test('payment 503 is retried with the same idempotency key, then reported; nothing is recorded', async () => {
  const id = await s.toFeesAssessed();
  await s.fault('payment', { status: 503 });
  const r = await s.api('POST', `/permits/${id}/payments`);
  assert.equal(r.status, 503);
  const posts = (await s.calls('payment')).filter((c) => c.method === 'POST');
  assert.equal(posts.length, 3);
  assert.equal(new Set(posts.map((c) => c.idempotencyKey)).size, 1, 'every retry reuses one key: no double charge');
  const p = await s.get(id);
  assert.equal(p.payment, null);
  assert.equal(p.status, 'fees_assessed');
});

test('a notification 500 leaves the message in the outbox; a flush after recovery sends it', async () => {
  await s.fault('notify', { status: 500 });
  const id = await s.toFeesAssessed();
  await s.api('POST', '/admin/outbox/flush');
  let [entry] = (await s.api('GET', `/admin/outbox?permitId=${id}`)).body.entries;
  assert.equal(entry.status, 'pending');
  assert.match(entry.lastError, /HTTP 500/);
  await s.reset();
  await s.api('POST', '/admin/outbox/flush');
  [entry] = (await s.api('GET', `/admin/outbox?permitId=${id}`)).body.entries;
  assert.equal(entry.status, 'sent');
  assert.equal(entry.template, 'fees_due');
});

test('a notification that keeps failing is dead-lettered after 5 attempts', async () => {
  await s.fault('notify', { status: 503 });
  const id = await s.toFeesAssessed();
  const entry = await waitFor(async () => {
    await s.api('POST', '/admin/outbox/flush');
    const [e] = (await s.api('GET', `/admin/outbox?permitId=${id}`)).body.entries;
    return e.status === 'dead' && e;
  });
  assert.equal(entry.attempts, 5);
  const h = (await s.api('GET', '/health')).body;
  assert.ok(h.outbox.dead >= 1, 'dead letters are visible in /health');
  assert.equal((await s.get(id)).status, 'fees_assessed', 'the workflow itself was never blocked');
});

test('a document service 500 fails the upload once (no retry) and records nothing', async () => {
  const c = await s.api('POST', '/permits', { permitType: 'electrical', applicant: { email: 'e@example.org' } });
  await s.fault('documents', { status: 500 });
  const r = await s.api('POST', `/permits/${c.body.id}/documents`, { type: 'load_calculation', filename: 'load.pdf', contentBase64: PDF });
  assert.equal(r.status, 503);
  assert.equal((await s.calls('documents')).length, 1);
  assert.equal((await s.get(c.body.id)).documents.length, 0);
});

test('deep health reports a downstream outage as degraded', async () => {
  assert.equal((await s.api('GET', '/health?deep=1')).body.status, 'ok');
  await s.fault('payment', { status: 503 });
  const h = (await s.api('GET', '/health?deep=1')).body;
  assert.equal(h.status, 'degraded');
  assert.match(h.dependencies.payment, /^down/);
  assert.equal(h.dependencies.gis, 'up');
});

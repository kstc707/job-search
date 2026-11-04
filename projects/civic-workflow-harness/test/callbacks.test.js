// Duplicate, replayed, out-of-order and forged payment callbacks.
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { startStack, waitFor } from './helpers.js';

let s;
before(async () => { s = await startStack(); });
after(() => s.close());
beforeEach(() => s.reset());

const count = (arr, pred) => arr.filter(pred).length;

test('a signed callback moves the permit from fees_assessed to paid', async () => {
  const id = await s.toFeesAssessed();
  const pay = await s.api('POST', `/permits/${id}/payments`);
  assert.equal(pay.status, 202);
  assert.equal(pay.body.permit.payment.status, 'pending');
  const p = await waitFor(async () => { const x = await s.get(id); return x.status === 'paid' && x; });
  assert.equal(p.payment.status, 'succeeded');
  assert.deepEqual(p.payment.appliedEventIds.length, 2);
});

test('the same event delivered three times is applied once', async () => {
  await s.fault('payment', { duplicateCallbacks: 3 });
  const id = await s.toFeesAssessed();
  await s.api('POST', `/permits/${id}/payments`);
  await waitFor(async () => (await s.deliveries()).length === 6);
  const d = await s.deliveries();
  assert.equal(count(d, (x) => x.response?.applied), 2, 'pending + succeeded each applied once');
  assert.equal(count(d, (x) => x.response?.duplicate), 4);
  const p = await s.get(id);
  assert.equal(p.status, 'paid');
  assert.equal(count(p.history, (h) => h.action === 'payment_received'), 1);
  const out = (await s.api('GET', `/admin/outbox?permitId=${id}`)).body.entries;
  assert.equal(count(out, (e) => e.template === 'payment_received'), 1, 'one receipt, not three');
});

test('five concurrent copies of one event: exactly one is applied', async () => {
  await s.fault('payment', { suppressCallbacks: true });
  const id = await s.toFeesAssessed();
  await s.api('POST', `/permits/${id}/payments`);
  const ev = s.eventFor(await s.get(id));
  const results = await Promise.all(Array.from({ length: 5 }, () => s.callback(ev)));
  assert.ok(results.every((r) => r.status === 200));
  assert.equal(count(results, (r) => r.body.applied), 1);
  assert.equal(count(results, (r) => r.body.duplicate), 4);
  const p = await s.get(id);
  assert.equal(count(p.history, (h) => h.action === 'payment_received'), 1);
});

test('succeeded arriving before pending keeps the permit paid; the late event is stale', async () => {
  await s.fault('payment', { outOfOrder: true });
  const id = await s.toFeesAssessed();
  await s.api('POST', `/permits/${id}/payments`);
  await waitFor(async () => (await s.deliveries()).length === 2);
  const [first, second] = await s.deliveries();
  assert.equal(first.type, 'charge.succeeded');
  assert.equal(second.response.stale, true);
  const p = await s.get(id);
  assert.equal(p.status, 'paid');
  assert.equal(p.payment.status, 'succeeded', 'the stale pending event did not downgrade the payment');
  assert.equal(p.payment.staleEventIds.length, 1);
});

test('an old event replayed after the permit moved on does not regress it', async () => {
  const id = await s.toPaid();
  await s.api('POST', `/permits/${id}/transitions`, { action: 'start_review' });
  const p = await s.get(id);
  const replay = await s.callback(s.eventFor(p, { id: p.payment.appliedEventIds[1] }));
  assert.equal(replay.body.duplicate, true);
  const lateNewId = await s.callback(s.eventFor(p, { type: 'charge.pending', sequence: 1, id: 'evt_late_retry' }));
  assert.equal(lateNewId.body.stale, true);
  const after = await s.get(id);
  assert.equal(after.status, 'in_review');
  assert.equal(after.payment.status, 'succeeded');
});

test('rejects a callback signed with the wrong secret and records nothing', async () => {
  await s.fault('payment', { suppressCallbacks: true });
  const id = await s.toFeesAssessed();
  await s.api('POST', `/permits/${id}/payments`);
  const ev = s.eventFor(await s.get(id));
  const r = await s.callback(ev, { secret: 'attacker-guess' });
  assert.equal(r.status, 401);
  const ok = await s.callback(ev);
  assert.equal(ok.body.applied, true, 'the forged attempt did not burn the event id');
});

test('rejects a callback with no signature header', async () => {
  const r = await s.callback({ id: 'evt_x', type: 'charge.succeeded', sequence: 2, idempotencyKey: 'k' }, { signature: null });
  assert.equal(r.status, 401);
  assert.equal(r.body.error.code, 'unauthorized');
});

test('rejects a correctly signed body that is not JSON or not an event', async () => {
  const bad = await s.callback('{"id": "evt_1", "type":');
  assert.equal(bad.status, 400);
  assert.equal(bad.body.error.code, 'malformed_json');
  const incomplete = await s.callback({ id: 'evt_2', type: 'charge.refunded' });
  assert.equal(incomplete.status, 400);
  assert.equal(incomplete.body.error.code, 'invalid_event');
});

test('an amount mismatch does not mark the permit paid and opens a reconciliation item', async () => {
  await s.fault('payment', { amountDeltaCents: -100 });
  const id = await s.toFeesAssessed();
  await s.api('POST', `/permits/${id}/payments`);
  await waitFor(async () => (await s.deliveries()).length === 2);
  const p = await s.get(id);
  assert.equal(p.status, 'fees_assessed');
  assert.equal(p.payment.status, 'disputed');
  const items = (await s.api('GET', '/admin/reconciliation')).body.items.filter((r) => r.permitId === id);
  assert.equal(items.length, 1);
  assert.equal(items[0].reason, 'amount_mismatch');
  assert.equal(items[0].expectedCents - items[0].receivedCents, 100);
});

test('a failed charge leaves the permit payable and the retry uses a new idempotency key', async () => {
  await s.fault('payment', { failCharge: true });
  const id = await s.toFeesAssessed();
  await s.api('POST', `/permits/${id}/payments`);
  await waitFor(async () => (await s.get(id)).payment.status === 'failed');
  assert.equal((await s.get(id)).status, 'fees_assessed');
  await s.reset();
  await s.api('POST', `/permits/${id}/payments`);
  const p = await waitFor(async () => { const x = await s.get(id); return x.status === 'paid' && x; });
  assert.equal(p.payment.attempt, 2);
  const keys = (await s.calls('payment')).filter((c) => c.method === 'POST').map((c) => c.idempotencyKey);
  assert.deepEqual(keys, [p.payment.idempotencyKey]);
  assert.match(p.payment.idempotencyKey, /-2-[0-9a-f]{8}$/);
});

test('an event for an unknown permit or charge is recorded as an orphan, not applied', async () => {
  const r = await s.callback({ id: 'evt_orphan_1', type: 'charge.succeeded', sequence: 2, permitId: 'PRM-424242', idempotencyKey: 'pay-nope', amountCents: 100 });
  assert.equal(r.status, 200);
  assert.equal(r.body.orphan, true);
  const again = await s.callback({ id: 'evt_orphan_1', type: 'charge.succeeded', sequence: 2, permitId: 'PRM-424242', idempotencyKey: 'pay-nope', amountCents: 100 });
  assert.equal(again.body.duplicate, true);
});

test('two simultaneous payment requests (double-click) create one charge', async () => {
  const id = await s.toFeesAssessed();
  const [a, b] = await Promise.all([s.api('POST', `/permits/${id}/payments`), s.api('POST', `/permits/${id}/payments`)]);
  assert.equal(a.status, 202);
  assert.equal(b.status, 202);
  assert.equal([a.body.reused, b.body.reused].filter(Boolean).length, 1);
  await waitFor(async () => (await s.get(id)).status === 'paid');
  const posts = (await s.calls('payment')).filter((c) => c.method === 'POST');
  assert.equal(posts.length, 1);
});

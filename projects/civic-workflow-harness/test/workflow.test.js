// Happy path and state machine rules.
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { startStack, PDF } from './helpers.js';
import { calculateInvoice } from '../src/workflow/fees.js';
import { loadConfig } from '../src/config.js';

let s;
before(async () => { s = await startStack(); });
after(() => s.close());
beforeEach(() => s.reset());

test('full lifecycle: draft to finaled, with ordered history and one notification per step', async () => {
  const id = await s.toPaid();
  for (const action of ['start_review', 'approve', 'issue']) {
    const r = await s.api('POST', `/permits/${id}/transitions`, { action });
    assert.equal(r.status, 200, `${action}: ${r.text}`);
  }
  await s.api('POST', `/permits/${id}/inspections`, { type: 'framing', result: 'pass', inspector: 'J. Okafor' });
  const fin = await s.api('POST', `/permits/${id}/inspections`, { type: 'final', result: 'pass', inspector: 'J. Okafor' });
  assert.equal(fin.status, 201);
  const p = await s.get(id);
  assert.equal(p.status, 'finaled');
  assert.deepEqual(p.history.map((h) => h.to), ['draft', 'submitted', 'fees_assessed', 'paid', 'in_review', 'approved', 'issued', 'finaled']);
  assert.deepEqual(p.allowedActions, []);
  await s.api('POST', '/admin/outbox/flush');
  const templates = (await s.api('GET', `/admin/outbox?permitId=${id}`)).body.entries.map((e) => `${e.template}:${e.status}`);
  assert.deepEqual(templates, ['fees_due:sent', 'payment_received:sent', 'permit_approved:sent', 'permit_issued:sent', 'permit_finaled:sent']);
});

test('fees follow config/fees.json: valuation rate, minimum fee, flat fee, technology fee', () => {
  const { fees } = loadConfig();
  const building = calculateInvoice({ permitType: 'building', valuation: 100000 }, fees, 'INV-1');
  assert.deepEqual(building.lines.map((l) => [l.code, l.amountCents]), [['BASE', 15000], ['VALUATION', 75000], ['TECH', 3600]]);
  assert.equal(building.totalCents, 93600);
  const smallDemo = calculateInvoice({ permitType: 'demolition', valuation: 5000 }, fees, 'INV-2');
  assert.deepEqual(smallDemo.lines.map((l) => l.code), ['BASE', 'VALUATION', 'MINIMUM', 'TECH']);
  assert.equal(smallDemo.totalCents, 15000 + 600);
  const electrical = calculateInvoice({ permitType: 'electrical', valuation: null }, fees, 'INV-3');
  assert.equal(electrical.totalCents, 9360);
});

test('invalid transitions are 409 and list the actions that are allowed', async () => {
  const id = await s.createReady();
  const approve = await s.api('POST', `/permits/${id}/transitions`, { action: 'approve' });
  assert.equal(approve.status, 409);
  assert.equal(approve.body.error.code, 'invalid_transition');
  const system = await s.api('POST', `/permits/${id}/transitions`, { action: 'payment_received' });
  assert.equal(system.status, 400, 'system transitions cannot be requested by a client');
  const inspect = await s.api('POST', `/permits/${id}/inspections`, { type: 'final', result: 'pass', inspector: 'X' });
  assert.equal(inspect.status, 409);
  const pay = await s.api('POST', `/permits/${id}/payments`);
  assert.equal(pay.status, 409);
  assert.equal((await s.get(id)).status, 'draft');
});

test('a failed final inspection keeps the permit issued; rejection needs a reason and is terminal', async () => {
  const a = await s.toPaid();
  for (const action of ['start_review', 'approve', 'issue']) await s.api('POST', `/permits/${a}/transitions`, { action });
  await s.api('POST', `/permits/${a}/inspections`, { type: 'final', result: 'fail', inspector: 'J. Okafor', notes: 'GFCI missing' });
  const pa = await s.get(a);
  assert.equal(pa.status, 'issued');
  assert.equal(pa.inspections.length, 1);

  const b = await s.toPaid();
  await s.api('POST', `/permits/${b}/transitions`, { action: 'start_review' });
  const noReason = await s.api('POST', `/permits/${b}/transitions`, { action: 'reject' });
  assert.equal(noReason.status, 422);
  const rej = await s.api('POST', `/permits/${b}/transitions`, { action: 'reject', reason: 'Setback violation' });
  assert.equal(rej.body.status, 'rejected');
  assert.deepEqual(rej.body.allowedActions, []);
  const issue = await s.api('POST', `/permits/${b}/transitions`, { action: 'issue' });
  assert.equal(issue.status, 409);
});

test('a high-risk flood zone parcel requires an elevation certificate (v1.1)', async () => {
  const id = await s.createReady({ parcelId: 'P-1002' });
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 422);
  assert.deepEqual(r.body.error.details.missingDocuments, ['elevation_certificate']);
  await s.api('POST', `/permits/${id}/documents`, { type: 'elevation_certificate', filename: 'ec.pdf', contentBase64: PDF });
  const ok = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(ok.status, 200);
  assert.equal(ok.body.floodZone, 'AE');
});

test('permits, processed events and the outbox survive an app restart', async () => {
  const id = await s.toPaid();
  const before = await s.get(id);
  await s.restartApp();
  const after = await s.get(id);
  assert.deepEqual(after, before);
  const replay = await s.callback(s.eventFor(after, { id: after.payment.appliedEventIds[1] }));
  assert.equal(replay.body.duplicate, true, 'dedup state is durable, not in memory');
});

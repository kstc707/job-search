// Missing and invalid fields: every bad input gets a precise 4xx and changes nothing.
import { test, before, after, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { startStack, validBuilding, PDF } from './helpers.js';

let s;
before(async () => { s = await startStack(); });
after(() => s.close());
beforeEach(() => s.reset());

const fields = (res) => res.body.error.details.errors.map((e) => e.field);

test('rejects a permit with no permitType', async () => {
  const r = await s.api('POST', '/permits', validBuilding({ permitType: undefined }));
  assert.equal(r.status, 400);
  assert.equal(r.body.error.code, 'invalid_fields');
  assert.deepEqual(fields(r), ['permitType']);
});

test('rejects an unknown permitType', async () => {
  const r = await s.api('POST', '/permits', validBuilding({ permitType: 'swimming_pool' }));
  assert.equal(r.status, 400);
  assert.deepEqual(fields(r), ['permitType']);
  assert.match(r.body.error.details.errors[0].message, /building, electrical, demolition/);
});

test('rejects a permit with no applicant email', async () => {
  const r = await s.api('POST', '/permits', validBuilding({ applicant: { name: 'No Email' } }));
  assert.equal(r.status, 400);
  assert.deepEqual(fields(r), ['applicant.email']);
});

test('rejects a malformed applicant email', async () => {
  const r = await s.api('POST', '/permits', validBuilding({ applicant: { name: 'X', email: 'not-an-email' } }));
  assert.equal(r.status, 400);
  assert.deepEqual(fields(r), ['applicant.email']);
});

test('reports every malformed field in one response (valuation, parcel id)', async () => {
  const r = await s.api('POST', '/permits', validBuilding({ valuation: -5, parcelId: '1001' }));
  assert.equal(r.status, 400);
  assert.deepEqual(fields(r).sort(), ['parcelId', 'valuation']);
  const r2 = await s.api('POST', '/permits', validBuilding({ valuation: 'a lot' }));
  assert.deepEqual(fields(r2), ['valuation']);
});

test('rejects a body that is not JSON', async () => {
  const r = await s.api('POST', '/permits', '{"permitType": "building",');
  assert.equal(r.status, 400);
  assert.equal(r.body.error.code, 'malformed_json');
});

test('submit lists every missing required field and leaves the permit in draft', async () => {
  const c = await s.api('POST', '/permits', { permitType: 'building', applicant: { email: 'min@example.org' } });
  assert.equal(c.status, 201);
  const r = await s.api('POST', `/permits/${c.body.id}/submit`);
  assert.equal(r.status, 422);
  assert.equal(r.body.error.code, 'missing_fields');
  assert.deepEqual(r.body.error.details.missingFields, ['applicant.name', 'parcelId', 'description', 'valuation']);
  assert.equal((await s.get(c.body.id)).status, 'draft');
  assert.equal((await s.calls('gis')).length, 0, 'GIS is not called when fields are missing');
});

test('submit lists missing required documents', async () => {
  const id = await s.createReady({}, ['site_plan']);
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 422);
  assert.equal(r.body.error.code, 'missing_documents');
  assert.deepEqual(r.body.error.details.missingDocuments, ['construction_drawings']);
  const p = await s.get(id);
  assert.equal(p.status, 'draft');
  assert.equal(p.parcel, undefined, 'GIS result from the failed submit was not committed');
});

test('filling the missing fields with PATCH lets the same permit submit', async () => {
  const c = await s.api('POST', '/permits', { permitType: 'building', applicant: { email: 'fix@example.org' } });
  const id = c.body.id;
  for (const type of ['site_plan', 'construction_drawings']) {
    await s.api('POST', `/permits/${id}/documents`, { type, filename: 'f.pdf', contentBase64: PDF });
  }
  const patch = await s.api('PATCH', `/permits/${id}`, { applicant: { name: 'Fixed Name' }, parcelId: 'P-1004', description: 'Garage', valuation: 20000 });
  assert.equal(patch.status, 200);
  assert.equal(patch.body.applicant.email, 'fix@example.org', 'PATCH merges applicant fields');
  const r = await s.api('POST', `/permits/${id}/submit`);
  assert.equal(r.status, 200);
  assert.equal(r.body.status, 'fees_assessed');
  const locked = await s.api('PATCH', `/permits/${id}`, { description: 'too late' });
  assert.equal(locked.status, 409);
});

test('rejects documents with an unknown type, no filename or empty content', async () => {
  const c = await s.api('POST', '/permits', validBuilding());
  const r = await s.api('POST', `/permits/${c.body.id}/documents`, { type: 'selfie', contentBase64: '' });
  assert.equal(r.status, 400);
  assert.deepEqual(fields(r).sort(), ['contentBase64', 'filename', 'type']);
  assert.equal((await s.calls('documents')).length, 0, 'nothing sent to the document service');
  assert.equal((await s.get(c.body.id)).documents.length, 0);
});

test('SMS notifications require a phone number; unknown permit ids are 404', async () => {
  const r = await s.api('POST', '/permits', validBuilding({ applicant: { name: 'T', email: 't@example.org', notifyChannel: 'sms' } }));
  assert.equal(r.status, 400);
  assert.deepEqual(fields(r), ['applicant.phone']);
  const nf = await s.api('GET', '/permits/PRM-999999');
  assert.equal(nf.status, 404);
  assert.equal(nf.body.error.code, 'not_found');
});

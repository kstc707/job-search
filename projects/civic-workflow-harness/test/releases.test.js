// Schema migrations and release/schema compatibility (what deploy and rollback depend on).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { loadMigrations, migrate } from '../src/store/migrations.js';
import { createApp } from '../src/app.js';
import { startStack, validBuilding } from './helpers.js';

const migrations = await loadMigrations();
const v1 = () => {
  const s = migrate({ schemaVersion: 0 }, 1, migrations).state;
  s.permits['PRM-000001'] = { id: 'PRM-000001', status: 'draft', applicant: { name: 'Old', email: 'old@example.org' }, documents: [], history: [] };
  return s;
};

test('migration 002 up adds flood zone and channel defaults to existing permits', () => {
  const { state, applied } = migrate(v1(), 2, migrations);
  assert.deepEqual(applied, ['up 2']);
  assert.equal(state.schemaVersion, 2);
  assert.equal(state.permits['PRM-000001'].floodZone, null);
  assert.equal(state.permits['PRM-000001'].applicant.notifyChannel, 'email');
  assert.equal(state.permits['PRM-000001'].applicant.name, 'Old');
});

test('migration 002 down keeps post-upgrade permits, re-addresses SMS to email, and up restores', () => {
  const s2 = migrate(v1(), 2, migrations).state;
  s2.permits['PRM-000002'] = { id: 'PRM-000002', status: 'fees_assessed', floodZone: 'AE', applicant: { name: 'New', email: 'new@example.org', phone: '+15551234567', notifyChannel: 'sms' }, documents: [], history: [] };
  s2.outbox.push({ id: 'msg-000001', permitId: 'PRM-000002', channel: 'sms', to: '+15551234567', status: 'pending' });
  const down = migrate(s2, 1, migrations).state;
  assert.equal(down.schemaVersion, 1);
  assert.deepEqual(Object.keys(down.permits), ['PRM-000001', 'PRM-000002'], 'nothing created after the upgrade is lost');
  assert.equal(down.permits['PRM-000002'].floodZone, undefined);
  assert.equal(down.permits['PRM-000002'].applicant.notifyChannel, undefined);
  assert.deepEqual([down.outbox[0].channel, down.outbox[0].to], ['email', 'new@example.org']);
  const up = migrate(down, 2, migrations).state;
  assert.equal(up.permits['PRM-000002'].floodZone, 'AE');
  assert.equal(up.permits['PRM-000002'].applicant.notifyChannel, 'sms');
  assert.deepEqual([up.outbox[0].channel, up.outbox[0].to], ['sms', '+15551234567']);
  assert.equal(up.archive002, undefined);
});

test('a release refuses to start on a store that is newer than it, or older without migrating', async () => {
  const dataDir = mkdtempSync(join(tmpdir(), 'cwh-rel-'));
  try {
    const base = { dataDir, downstream: { gis: 'http://127.0.0.1:9', payment: 'http://127.0.0.1:9', documents: 'http://127.0.0.1:9', notify: 'http://127.0.0.1:9' }, webhookSecret: 'x', log: () => {} };
    const v2 = await createApp({ ...base, release: { version: '1.1.0', schemaVersion: 2 } });
    await v2.close();
    await assert.rejects(createApp({ ...base, release: { version: '1.0.0', schemaVersion: 1 } }), (e) => e.code === 'schema_mismatch' && /newer/.test(e.message));
    const other = mkdtempSync(join(tmpdir(), 'cwh-rel-'));
    const old = await createApp({ ...base, dataDir: other, release: { version: '1.0.0', schemaVersion: 1 } });
    await old.close();
    await assert.rejects(createApp({ ...base, dataDir: other, release: { version: '1.1.0', schemaVersion: 2 } }), (e) => e.code === 'schema_mismatch' && /Run migrations/.test(e.message));
    rmSync(other, { recursive: true, force: true });
  } finally {
    rmSync(dataDir, { recursive: true, force: true });
  }
});

test('a schema-1 release (v1.0.0) ignores v1.1 fields and never asks for flood documents', async () => {
  const s = await startStack({ schemaVersion: 1 });
  try {
    const c = await s.api('POST', '/permits', validBuilding({ applicant: { name: 'A', email: 'a@example.org', notifyChannel: 'sms' } }));
    assert.equal(c.status, 201);
    assert.equal(c.body.applicant.notifyChannel, undefined);
    assert.equal('floodZone' in c.body, false);
    const id = await s.createReady({ parcelId: 'P-1002' });
    const r = await s.api('POST', `/permits/${id}/submit`);
    assert.equal(r.body.status, 'fees_assessed', 'flood-zone rule is a v1.1 feature');
    assert.equal(r.body.floodZone, undefined);
    assert.deepEqual((await s.api('GET', '/version')).body.features, { floodZone: false, notifyChannel: false });
  } finally {
    await s.close();
  }
});

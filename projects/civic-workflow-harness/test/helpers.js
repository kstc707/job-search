// Test stack: a fault-injecting mock downstream + the app on ephemeral ports + a temp data dir.
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startMock } from '../mocks/downstream.js';
import { createApp } from '../src/app.js';
import { sign } from '../src/lib/signature.js';

export const SECRET = 'test-webhook-secret';
export const PDF = Buffer.from('%PDF-1.4 test document').toString('base64');

export const validBuilding = (over = {}) => ({
  permitType: 'building',
  applicant: { name: 'Dana Rivera', email: 'dana@example.org' },
  parcelId: 'P-1001',
  description: 'Two-story rear addition',
  valuation: 100000,
  ...over,
});

export async function waitFor(fn, { timeoutMs = 3000, intervalMs = 20 } = {}) {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error('waitFor: condition not met in time');
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export async function startStack({ schemaVersion = 2, timeoutMs = 200, backoffMs = 10, maxNotifyAttempts = 5, dataDir, keepData = false } = {}) {
  const mock = await startMock({ webhookSecret: SECRET });
  dataDir ??= mkdtempSync(join(tmpdir(), 'cwh-test-'));
  const opts = {
    dataDir,
    release: { version: `test-schema${schemaVersion}`, schemaVersion },
    downstream: mock.urls,
    webhookSecret: SECRET,
    timeoutMs,
    backoffMs,
    maxNotifyAttempts,
    autoMigrate: true,
    log: () => {},
  };
  let app = await createApp(opts);
  await app.listen(0);

  const api = async (method, path, body, headers = {}) => {
    const res = await fetch(app.url + path, {
      method,
      headers: { 'content-type': 'application/json', ...headers },
      body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
    });
    const text = await res.text();
    let json = null;
    try { json = text ? JSON.parse(text) : null; } catch { /* non-JSON */ }
    return { status: res.status, body: json, text };
  };
  const mockCall = async (method, path, body) => (await fetch(mock.url + path, { method, body: body && JSON.stringify(body) })).json();

  const stack = {
    mock,
    api,
    get app() { return app; },
    dataDir,
    fault: (service, spec) => mockCall('POST', '/__faults', { service, ...spec }),
    reset: async () => { await mockCall('DELETE', '/__faults'); await mockCall('DELETE', '/__calls'); },
    calls: async (service) => (await mockCall('GET', `/__calls?service=${service}`)).calls,
    deliveries: async () => (await mockCall('GET', '/__deliveries')).deliveries,
    get: async (id) => (await api('GET', `/permits/${id}`)).body,
    /** POST a signed payment event the way the provider would. */
    callback: (event, { secret = SECRET, signature } = {}) => {
      const raw = typeof event === 'string' ? event : JSON.stringify(event);
      return api('POST', '/callbacks/payment', raw, signature === null ? {} : { 'x-signature': signature ?? sign(secret, raw) });
    },
    async createReady(over = {}, docs = ['site_plan', 'construction_drawings']) {
      const c = await api('POST', '/permits', validBuilding(over));
      if (c.status !== 201) throw new Error(`create failed: ${c.text}`);
      for (const type of docs) {
        const d = await api('POST', `/permits/${c.body.id}/documents`, { type, filename: `${type}.pdf`, contentBase64: PDF });
        if (d.status !== 201) throw new Error(`doc failed: ${d.text}`);
      }
      return c.body.id;
    },
    async toFeesAssessed(over) {
      const id = await stack.createReady(over);
      const s = await api('POST', `/permits/${id}/submit`);
      if (s.body?.status !== 'fees_assessed') throw new Error(`submit failed: ${s.text}`);
      return id;
    },
    async toPaid(over) {
      const id = await stack.toFeesAssessed(over);
      await api('POST', `/permits/${id}/payments`);
      await waitFor(async () => (await stack.get(id)).status === 'paid');
      return id;
    },
    eventFor(permit, { type = 'charge.succeeded', sequence = 2, id, amountCents } = {}) {
      return {
        id: id ?? `evt_manual_${permit.id}_${type}_${sequence}`,
        type,
        sequence,
        chargeId: permit.payment.chargeId,
        permitId: permit.id,
        idempotencyKey: permit.payment.idempotencyKey,
        amountCents: amountCents ?? permit.payment.amountCents,
        currency: 'USD',
      };
    },
    async restartApp() {
      await app.close();
      app = await createApp(opts);
      await app.listen(0);
    },
    async close() {
      await app.close();
      await mock.close();
      if (!keepData) rmSync(dataDir, { recursive: true, force: true });
    },
  };
  return stack;
}

#!/usr/bin/env node
// One mock server standing in for four downstream systems, mounted under path prefixes:
//   /payment   charges with Idempotency-Key dedup + signed webhooks back to the caller
//   /gis       parcel layer (zoning, district, flood zone)
//   /documents file storage
//   /notify    email/SMS gateway with Idempotency-Key dedup
// Fault injection (tests and rehearsals drive it over HTTP):
//   POST   /__faults {service, latencyMs?, hang?, status?, malformed?, count?}   request faults
//   POST   /__faults {service:"payment", duplicateCallbacks?, outOfOrder?, failCharge?,
//                     amountDeltaCents?, callbackDelayMs?, suppressCallbacks?}    webhook behaviour
//   DELETE /__faults            clear all faults
//   GET    /__calls[?service=]  request log (for asserting retries / idempotency keys)
//   DELETE /__calls             clear the log
//   GET    /__deliveries        webhook deliveries and the app's responses
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { sign } from '../src/lib/signature.js';

const SERVICES = ['payment', 'gis', 'documents', 'notify'];
const REQUEST_FAULT_KEYS = ['latencyMs', 'hang', 'status', 'malformed'];
const CALLBACK_KEYS = ['duplicateCallbacks', 'outOfOrder', 'failCharge', 'amountDeltaCents', 'callbackDelayMs', 'suppressCallbacks'];

export const PARCELS = {
  'P-1001': { parcelId: 'P-1001', zoning: 'R1', district: 'North', floodZone: 'X' },
  'P-1002': { parcelId: 'P-1002', zoning: 'C1', district: 'Central', floodZone: 'AE' },
  'P-1003': { parcelId: 'P-1003', zoning: 'I1', district: 'East', floodZone: 'X' },
  'P-1004': { parcelId: 'P-1004', zoning: 'R2', district: 'South', floodZone: 'X' },
  'P-1005': { parcelId: 'P-1005', zoning: 'AG', district: 'West', floodZone: 'A' },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function startMock({ port = 0, host = '127.0.0.1', webhookSecret = 'dev-webhook-secret' } = {}) {
  const st = { faults: {}, callbacks: {}, calls: [], deliveries: [], charges: new Map(), messages: new Map(), files: 0, chargeSeq: 0 };
  const pendingTimers = new Set();

  const send = (res, status, body) => {
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  };

  function takeFault(service) {
    const f = st.faults[service];
    if (!f) return null;
    if (f.remaining !== Infinity) {
      f.remaining -= 1;
      if (f.remaining <= 0) delete st.faults[service];
    }
    return f;
  }

  async function deliver(charge, callbackUrl) {
    const b = st.callbacks.payment ?? {};
    await sleep(b.callbackDelayMs ?? 20);
    const final = b.failCharge ? 'failed' : 'succeeded';
    charge.status = final;
    charge.sequence = 2;
    if (b.suppressCallbacks || !callbackUrl) return;
    const base = { chargeId: charge.id, permitId: charge.permitId, idempotencyKey: charge.idempotencyKey, currency: charge.currency };
    const events = [
      { ...base, id: `evt_${charge.id}_1`, type: 'charge.pending', sequence: 1, amountCents: charge.amountCents },
      { ...base, id: `evt_${charge.id}_2`, type: `charge.${final}`, sequence: 2, amountCents: charge.amountCents + (b.amountDeltaCents ?? 0), ...(final === 'failed' ? { reason: 'card_declined' } : {}) },
    ];
    const order = b.outOfOrder ? events.reverse() : events;
    for (const ev of order) {
      for (let i = 0; i < (b.duplicateCallbacks ?? 1); i++) {
        const raw = JSON.stringify({ ...ev, occurredAt: new Date().toISOString() });
        let status = null;
        let response = null;
        try {
          const r = await fetch(callbackUrl, { method: 'POST', headers: { 'content-type': 'application/json', 'x-signature': sign(webhookSecret, raw) }, body: raw, signal: AbortSignal.timeout(3000) });
          status = r.status;
          response = await r.json().catch(() => null);
        } catch (e) {
          response = { error: e.message };
        }
        st.deliveries.push({ eventId: ev.id, type: ev.type, attempt: i + 1, status, response });
      }
    }
  }

  async function route(service, method, path, query, body, headers, res) {
    if (path === '/health' && method === 'GET') return send(res, 200, { status: 'ok', service });
    if (service === 'gis') {
      const m = path.match(/^\/parcels\/([^/]+)$/);
      if (m && method === 'GET') {
        const p = PARCELS[decodeURIComponent(m[1])];
        return p ? send(res, 200, p) : send(res, 404, { error: 'parcel not found' });
      }
    }
    if (service === 'documents' && path === '/files' && method === 'POST') {
      if (!body?.permitId || !body?.contentBase64) return send(res, 422, { error: 'permitId and contentBase64 required' });
      st.files += 1;
      return send(res, 201, { docId: `doc_${st.files}`, sizeBytes: Buffer.from(body.contentBase64, 'base64').length });
    }
    if (service === 'payment' && path === '/charges') {
      if (method === 'GET') {
        const c = st.charges.get(query.get('idempotencyKey'));
        return c ? send(res, 200, c) : send(res, 404, { error: 'no charge for that idempotency key' });
      }
      if (method === 'POST') {
        const key = headers['idempotency-key'];
        if (!key) return send(res, 400, { error: 'Idempotency-Key header required' });
        if (st.charges.has(key)) return send(res, 200, st.charges.get(key));
        if (!Number.isInteger(body?.amountCents) || body.amountCents <= 0) return send(res, 422, { error: 'amountCents must be a positive integer' });
        st.chargeSeq += 1;
        const charge = { id: `ch_${st.chargeSeq}`, idempotencyKey: key, permitId: body.permitId, amountCents: body.amountCents, currency: body.currency ?? 'USD', status: 'pending', sequence: 1, createdAt: new Date().toISOString() };
        st.charges.set(key, charge);
        send(res, 201, charge);
        const t = setTimeout(() => {
          pendingTimers.delete(t);
          deliver(charge, body.callbackUrl).catch(() => {});
        }, 0);
        pendingTimers.add(t);
        return;
      }
    }
    if (service === 'notify' && path === '/messages') {
      if (method === 'GET') return send(res, 200, { messages: [...st.messages.values()] });
      if (method === 'POST') {
        const key = headers['idempotency-key'];
        if (!key) return send(res, 400, { error: 'Idempotency-Key header required' });
        if (!body?.to || !['email', 'sms'].includes(body?.channel)) return send(res, 422, { error: 'to and channel (email|sms) required' });
        if (st.messages.has(key)) return send(res, 200, st.messages.get(key));
        const msg = { messageId: key, to: body.to, channel: body.channel, template: body.template, at: new Date().toISOString() };
        st.messages.set(key, msg);
        return send(res, 202, msg);
      }
    }
    return send(res, 404, { error: `mock has no route ${method} /${service}${path}` });
  }

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://mock');
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const raw = Buffer.concat(chunks).toString('utf8');
    let body = null;
    try { body = raw ? JSON.parse(raw) : null; } catch { body = null; }

    if (url.pathname === '/__faults') {
      if (req.method === 'DELETE') { st.faults = {}; st.callbacks = {}; return send(res, 200, { cleared: true }); }
      if (req.method === 'GET') return send(res, 200, { faults: st.faults, callbacks: st.callbacks });
      if (req.method === 'POST') {
        if (!SERVICES.includes(body?.service)) return send(res, 400, { error: `service must be one of ${SERVICES.join(', ')}` });
        const reqFault = Object.fromEntries(REQUEST_FAULT_KEYS.filter((k) => body[k] !== undefined).map((k) => [k, body[k]]));
        const cb = Object.fromEntries(CALLBACK_KEYS.filter((k) => body[k] !== undefined).map((k) => [k, body[k]]));
        if (Object.keys(reqFault).length) st.faults[body.service] = { ...reqFault, remaining: body.count ?? Infinity };
        if (Object.keys(cb).length) st.callbacks[body.service] = { ...(st.callbacks[body.service] ?? {}), ...cb };
        return send(res, 200, { faults: st.faults, callbacks: st.callbacks });
      }
    }
    if (url.pathname === '/__calls') {
      if (req.method === 'DELETE') { st.calls = []; st.deliveries = []; return send(res, 200, { cleared: true }); }
      const svc = url.searchParams.get('service');
      return send(res, 200, { calls: st.calls.filter((c) => !svc || c.service === svc) });
    }
    if (url.pathname === '/__deliveries') return send(res, 200, { deliveries: st.deliveries });

    const [, service, ...rest] = url.pathname.split('/');
    if (!SERVICES.includes(service)) return send(res, 404, { error: 'unknown service' });
    const path = '/' + rest.join('/');
    st.calls.push({ service, method: req.method, path, idempotencyKey: req.headers['idempotency-key'] ?? null, at: Date.now() });

    const fault = takeFault(service);
    if (fault) {
      if (fault.latencyMs) await sleep(fault.latencyMs);
      if (fault.hang) return; // never answer; the caller's timeout must fire
      if (fault.status) return send(res, fault.status, { error: 'injected fault' });
      if (fault.malformed) {
        res.writeHead(200, { 'content-type': 'application/json' });
        return res.end('{"parcelId": "P-10');
      }
    }
    try {
      await route(service, req.method, path, url.searchParams, body, req.headers, res);
    } catch (e) {
      if (!res.headersSent) send(res, 500, { error: e.message });
    }
  });

  await new Promise((r) => server.listen(port, host, r));
  const url = `http://${host}:${server.address().port}`;
  return {
    url,
    urls: Object.fromEntries(SERVICES.map((s) => [s, `${url}/${s}`])),
    state: st,
    async close() {
      for (const t of pendingTimers) clearTimeout(t);
      await new Promise((r) => {
        server.close(r);
        server.closeAllConnections();
      });
    },
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const m = await startMock({ port: Number(process.env.MOCK_PORT ?? 4100), webhookSecret: process.env.WEBHOOK_SECRET ?? 'dev-webhook-secret' });
  console.log(`mock downstream listening on ${m.url} (${SERVICES.map((s) => '/' + s).join(', ')})`);
  const stop = () => m.close().then(() => process.exit(0));
  process.on('SIGTERM', stop);
  process.on('SIGINT', stop);
}

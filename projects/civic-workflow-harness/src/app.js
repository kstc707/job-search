// Wires config, store, adapters, workflow engine and the REST API together.
import http from 'node:http';
import { join } from 'node:path';
import { ROOT, loadConfig, loadRelease } from './config.js';
import { loadMigrations, latestVersion } from './store/migrations.js';
import { openStore } from './store/store.js';
import { createHttpClient } from './adapters/http.js';
import { createGisAdapter } from './adapters/gis.js';
import { createPaymentAdapter } from './adapters/payment.js';
import { createDocumentAdapter } from './adapters/document.js';
import { createNotificationAdapter } from './adapters/notification.js';
import { createEngine } from './workflow/engine.js';
import { resolveHooks } from './workflow/hooks/index.js';
import { createOutbox } from './outbox.js';
import { createService } from './service.js';
import { AppError, ValidationError, NotFoundError } from './errors.js';

const MAX_BODY_BYTES = 8 * 1024 * 1024;

export async function createApp(options = {}) {
  const root = options.root ?? ROOT;
  const migrations = await loadMigrations(join(root, 'src', 'store', 'migrations'));
  const latest = latestVersion(migrations);
  const release = { ...loadRelease(root, latest), ...(options.release ?? {}) };
  if (release.schemaVersion > latest) {
    throw new Error(`Release pins schema ${release.schemaVersion} but only migrations up to ${latest} are packaged`);
  }
  const config = options.config ?? loadConfig(root);
  const features = { floodZone: release.schemaVersion >= 2, notifyChannel: release.schemaVersion >= 2 };
  const store = await openStore({ dataDir: options.dataDir, codeSchemaVersion: release.schemaVersion, migrations, autoMigrate: options.autoMigrate ?? false });

  const ds = options.downstream;
  const client = (service, retries) =>
    createHttpClient({ service, baseUrl: ds[service], timeoutMs: options.timeoutMs ?? 2000, retries: options.retries?.[service] ?? retries, backoffMs: options.backoffMs ?? 50 });
  const adapters = {
    gis: createGisAdapter(client('gis', 2)),
    payment: createPaymentAdapter(client('payment', 2)),
    documents: createDocumentAdapter(client('documents', 0)),
    notify: createNotificationAdapter(client('notify', 0)),
  };
  const log = options.log ?? ((entry) => console.log(JSON.stringify({ at: new Date().toISOString(), ...entry })));
  const engine = createEngine(config.workflow, resolveHooks(config.workflow.eventHooks));
  const outbox = createOutbox({ store, notify: adapters.notify, maxAttempts: options.maxNotifyAttempts ?? 5, log });

  let publicUrl = options.publicUrl ?? null;
  const service = createService({ store, engine, adapters, config, features, webhookSecret: options.webhookSecret, publicUrl: () => publicUrl, outbox });
  const startedAt = Date.now();

  async function health(url) {
    const s = store.read();
    const body = {
      status: 'ok',
      version: release.version,
      schemaVersion: release.schemaVersion,
      storeSchemaVersion: s.schemaVersion,
      uptimeSec: Math.round((Date.now() - startedAt) / 1000),
      outbox: outbox.stats(s),
      openReconciliation: s.reconciliation.filter((r) => r.status === 'open').length,
    };
    if (url.searchParams.get('deep') === '1') {
      const names = Object.keys(adapters);
      const results = await Promise.all(names.map((n) => adapters[n].health()));
      body.dependencies = Object.fromEntries(names.map((n, i) => [n, results[i]]));
      if (results.some((r) => r !== 'up')) body.status = 'degraded';
    }
    return { status: 200, body };
  }

  const P = '([^/]+)';
  const routes = [
    ['GET', /^\/health$/, (r) => health(r.url)],
    ['GET', /^\/version$/, () => ({ body: { version: release.version, schemaVersion: release.schemaVersion, builtAt: release.builtAt ?? null, features } })],
    ['GET', /^\/permits$/, (r) => ({ body: { permits: service.listPermits({ status: r.url.searchParams.get('status'), tag: r.url.searchParams.get('tag') }) } })],
    ['POST', /^\/permits$/, async (r) => ({ status: 201, body: await service.createPermit(r.json()) })],
    ['GET', new RegExp(`^/permits/${P}$`), (r, id) => ({ body: service.getPermit(id) })],
    ['PATCH', new RegExp(`^/permits/${P}$`), async (r, id) => ({ body: await service.updatePermit(id, r.json()) })],
    ['POST', new RegExp(`^/permits/${P}/submit$`), async (r, id) => ({ body: await service.submit(id) })],
    ['POST', new RegExp(`^/permits/${P}/documents$`), async (r, id) => ({ status: 201, body: await service.addDocument(id, r.json()) })],
    ['POST', new RegExp(`^/permits/${P}/payments$`), async (r, id) => ({ status: 202, body: await service.requestPayment(id) })],
    ['POST', new RegExp(`^/permits/${P}/transitions$`), async (r, id) => ({ body: await service.transition(id, r.json()) })],
    ['POST', new RegExp(`^/permits/${P}/inspections$`), async (r, id) => ({ status: 201, body: await service.recordInspection(id, r.json()) })],
    ['POST', /^\/callbacks\/payment$/, async (r) => ({ body: await service.handlePaymentCallback(r.raw, r.headers['x-signature']) })],
    ['GET', /^\/admin\/outbox$/, (r) => ({ body: { ...outbox.stats(), entries: service.outboxEntries({ permitId: r.url.searchParams.get('permitId'), status: r.url.searchParams.get('status') }) } })],
    ['POST', /^\/admin\/outbox\/flush$/, async () => { await outbox.dispatch(); return { body: outbox.stats() }; }],
    ['GET', /^\/admin\/reconciliation$/, () => ({ body: { items: service.reconciliationItems() } })],
    ['POST', /^\/admin\/reconcile$/, async () => ({ body: await service.reconcile() })],
  ];

  function readBody(req) {
    return new Promise((resolve, reject) => {
      const chunks = [];
      let size = 0;
      req.on('data', (c) => {
        size += c.length;
        if (size > MAX_BODY_BYTES) {
          reject(new AppError('Request body too large', { status: 413, code: 'body_too_large' }));
          req.destroy();
        } else chunks.push(c);
      });
      req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
      req.on('error', reject);
    });
  }

  async function handle(req, res) {
    const url = new URL(req.url, 'http://localhost');
    let status = 200;
    let body;
    try {
      const matches = routes.filter(([, re]) => re.test(url.pathname));
      const route = matches.find(([m]) => m === req.method);
      if (!route) {
        if (matches.length) throw new AppError(`Method ${req.method} not allowed`, { status: 405, code: 'method_not_allowed' });
        throw new NotFoundError(`No route for ${url.pathname}`);
      }
      const raw = await readBody(req);
      const ctx = {
        url,
        raw,
        headers: req.headers,
        json() {
          if (raw.trim() === '') return undefined;
          try {
            return JSON.parse(raw);
          } catch {
            throw new ValidationError('Request body is not valid JSON', { code: 'malformed_json' });
          }
        },
      };
      const params = url.pathname.match(route[1]).slice(1).map(decodeURIComponent);
      const out = await route[2](ctx, ...params);
      status = out.status ?? 200;
      body = out.body;
    } catch (e) {
      if (e instanceof AppError) {
        status = e.status;
        body = { error: e.toJSON() };
      } else {
        status = 500;
        body = { error: { code: 'internal_error', message: 'Internal error' } };
        log({ msg: 'unhandled error', error: e.stack });
      }
    }
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  }

  const server = http.createServer((req, res) => {
    handle(req, res).catch((e) => {
      log({ msg: 'response failed', error: e.message });
      res.destroy();
    });
  });

  return {
    server,
    store,
    service,
    release,
    features,
    get url() {
      return publicUrl;
    },
    listen(port = 0, host = '127.0.0.1') {
      return new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(port, host, () => {
          if (!publicUrl) publicUrl = `http://${host}:${server.address().port}`;
          resolve(publicUrl);
        });
      });
    },
    async close() {
      await outbox.idle();
      await new Promise((r) => {
        server.close(r);
        server.closeAllConnections();
      });
    },
  };
}

#!/usr/bin/env node
// Process entry point. Configuration comes from environment variables (deploy/lib.js sets them).
import { createApp } from './app.js';

const env = process.env;
const port = Number(env.PORT ?? 3000);
const host = env.HOST ?? '127.0.0.1';
const mock = env.MOCK_URL ?? 'http://127.0.0.1:4100';

let app;
try {
  app = await createApp({
    dataDir: env.DATA_DIR ?? 'data',
    downstream: {
      payment: env.PAYMENT_URL ?? `${mock}/payment`,
      gis: env.GIS_URL ?? `${mock}/gis`,
      documents: env.DOCS_URL ?? `${mock}/documents`,
      notify: env.NOTIFY_URL ?? `${mock}/notify`,
    },
    webhookSecret: env.WEBHOOK_SECRET ?? 'dev-webhook-secret',
    publicUrl: env.PUBLIC_URL ?? `http://${host}:${port}`,
    timeoutMs: Number(env.ADAPTER_TIMEOUT_MS ?? 2000),
    autoMigrate: env.AUTO_MIGRATE === '1',
  });
  await app.listen(port, host);
} catch (e) {
  console.error(JSON.stringify({ at: new Date().toISOString(), msg: 'startup failed', code: e.code ?? null, error: e.message }));
  process.exit(2);
}
console.log(JSON.stringify({ at: new Date().toISOString(), msg: 'listening', url: app.url, version: app.release.version, schemaVersion: app.release.schemaVersion, pid: process.pid }));

let stopping = false;
async function shutdown(signal) {
  if (stopping) return;
  stopping = true;
  console.log(JSON.stringify({ at: new Date().toISOString(), msg: 'shutting down', signal }));
  const force = setTimeout(() => process.exit(1), 5000);
  force.unref();
  await app.close();
  process.exit(0);
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

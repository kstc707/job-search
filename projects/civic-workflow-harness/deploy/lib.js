// Deployment and rollback building blocks, shared by package.js, deploy.js, rollback.js and rehearse.js.
// Layout of a deploy directory (default .deploy/, git-ignored):
//   releases/<version>/   packaged artifact (src/, config/, package.json, release.json)
//   current.json          which release is live, the previous one, and the pre-deploy backup
//   data/store.json       the live data store
//   backups/              store snapshots taken before every deploy and rollback
//   env.json              runtime settings (port, downstream URLs, webhook secret)
//   app.pid / app.log     the running process
//   history.jsonl         one line per deploy/rollback
import { spawn, spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync, appendFileSync, copyFileSync, openSync, readdirSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runSmoke } from '../smoke/run.js';

export const PROJECT = join(dirname(fileURLToPath(import.meta.url)), '..');
const readJson = (f) => JSON.parse(readFileSync(f, 'utf8'));
const writeJson = (f, v) => writeFileSync(f, JSON.stringify(v, null, 2) + '\n');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function layout(deployDir = process.env.DEPLOY_DIR ?? join(PROJECT, '.deploy')) {
  return {
    dir: deployDir,
    releases: join(deployDir, 'releases'),
    current: join(deployDir, 'current.json'),
    data: join(deployDir, 'data'),
    store: join(deployDir, 'data', 'store.json'),
    backups: join(deployDir, 'backups'),
    env: join(deployDir, 'env.json'),
    pid: join(deployDir, 'app.pid'),
    log: join(deployDir, 'app.log'),
    history: join(deployDir, 'history.jsonl'),
    seed: join(deployDir, 'seed.json'),
  };
}

export function ensureEnv(L, overrides = {}) {
  mkdirSync(L.dir, { recursive: true });
  if (!existsSync(L.env) || Object.keys(overrides).length) {
    const mock = overrides.mockUrl ?? 'http://127.0.0.1:4100';
    const port = overrides.port ?? 3000;
    writeJson(L.env, {
      PORT: String(port),
      HOST: '127.0.0.1',
      PUBLIC_URL: `http://127.0.0.1:${port}`,
      PAYMENT_URL: `${mock}/payment`,
      GIS_URL: `${mock}/gis`,
      DOCS_URL: `${mock}/documents`,
      NOTIFY_URL: `${mock}/notify`,
      WEBHOOK_SECRET: overrides.webhookSecret ?? 'dev-webhook-secret',
      ADAPTER_TIMEOUT_MS: '2000',
    });
  }
  return readJson(L.env);
}

const baseUrlOf = (env) => env.PUBLIC_URL;

function hashTree(dir) {
  const h = createHash('sha256');
  const walk = (d) => {
    for (const name of readdirSync(d).sort()) {
      const p = join(d, name);
      if (statSync(p).isDirectory()) walk(p);
      else h.update(relative(dir, p)).update(readFileSync(p));
    }
  };
  walk(dir);
  return h.digest('hex').slice(0, 16);
}

/** Build releases/<version>/ from this checkout, shipping only the migrations up to the pinned schema. */
export function packageRelease(version, L = layout()) {
  const spec = readJson(join(PROJECT, 'deploy', 'releases.json'))[version];
  if (!spec) throw new Error(`Unknown release ${version}; see deploy/releases.json`);
  const dest = join(L.releases, version);
  rmSync(dest, { recursive: true, force: true });
  mkdirSync(dest, { recursive: true });
  cpSync(join(PROJECT, 'src'), join(dest, 'src'), {
    recursive: true,
    filter: (src) => {
      const m = src.match(/migrations[\\/](\d{3})_[\w-]+\.js$/);
      return !m || Number(m[1]) <= spec.schemaVersion;
    },
  });
  cpSync(join(PROJECT, 'config'), join(dest, 'config'), { recursive: true });
  const pkg = readJson(join(PROJECT, 'package.json'));
  writeJson(join(dest, 'package.json'), { name: pkg.name, version, private: true, type: 'module' });
  const manifest = { version, schemaVersion: spec.schemaVersion, notes: spec.notes, builtAt: new Date().toISOString(), sourceHash: hashTree(join(dest, 'src')) };
  writeJson(join(dest, 'release.json'), manifest);
  return manifest;
}

export const manifest = (version, L = layout()) => {
  const f = join(L.releases, version, 'release.json');
  if (!existsSync(f)) throw new Error(`Release ${version} is not packaged (run: node deploy/package.js ${version})`);
  return readJson(f);
};
export const readCurrent = (L = layout()) => (existsSync(L.current) ? readJson(L.current) : null);
const storeSchema = (L) => (existsSync(L.store) ? readJson(L.store).schemaVersion : 0);
const history = (L, entry) => appendFileSync(L.history, JSON.stringify({ at: new Date().toISOString(), ...entry }) + '\n');

export function backupStore(L, label) {
  if (!existsSync(L.store)) return null;
  mkdirSync(L.backups, { recursive: true });
  const file = join(L.backups, `${new Date().toISOString().replace(/[:.]/g, '-')}-${label}.json`);
  copyFileSync(L.store, file);
  return file;
}

/**
 * Put a backup back as the live store, but never rewind the id counters: permit numbers issued after
 * the backup (now only in `snapshot`) must not be handed out again to different applicants.
 */
export function restoreBackup(L, backupFile, snapshotFile) {
  const restored = readJson(backupFile);
  if (snapshotFile && existsSync(snapshotFile)) {
    const later = readJson(snapshotFile).counters ?? {};
    for (const [k, v] of Object.entries(later)) restored.counters[k] = Math.max(restored.counters[k] ?? 0, v);
  }
  writeJson(L.store, restored);
}

/** Run a release's own migrate CLI against the live data dir. */
export function runMigrations(L, version, target) {
  const cli = join(L.releases, version, 'src', 'store', 'migrate-cli.js');
  const r = spawnSync(process.execPath, [cli, '--data', L.data, '--to', String(target)], { encoding: 'utf8' });
  return { ok: r.status === 0, output: (r.stdout + r.stderr).trim() };
}

const alive = (pid) => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

export async function stopApp(L) {
  if (!existsSync(L.pid)) return null;
  const { pid, version } = readJson(L.pid);
  if (alive(pid)) {
    process.kill(pid, 'SIGTERM');
    const end = Date.now() + 10000;
    while (alive(pid) && Date.now() < end) await sleep(50);
    if (alive(pid)) process.kill(pid, 'SIGKILL');
  }
  rmSync(L.pid, { force: true });
  return version;
}

export function startApp(L, version) {
  const env = ensureEnv(L);
  const entry = join(L.releases, version, 'src', 'server.js');
  const out = openSync(L.log, 'a');
  const child = spawn(process.execPath, [entry], { env: { ...process.env, ...env, DATA_DIR: L.data }, detached: true, stdio: ['ignore', out, out] });
  child.unref();
  writeJson(L.pid, { pid: child.pid, version, startedAt: new Date().toISOString() });
  return child.pid;
}

export async function waitHealthy(L, version, timeoutMs = 15000) {
  const env = ensureEnv(L);
  const { pid } = readJson(L.pid);
  const end = Date.now() + timeoutMs;
  let last = 'no answer';
  while (Date.now() < end) {
    if (!alive(pid)) throw new Error(`release ${version} exited during startup; tail of ${L.log}:\n${readFileSync(L.log, 'utf8').trim().split('\n').slice(-3).join('\n')}`);
    try {
      const r = await fetch(`${baseUrlOf(env)}/health`, { signal: AbortSignal.timeout(1000) });
      const h = await r.json();
      if (r.ok && h.version === version) return h;
      last = `${r.status} version=${h.version}`;
    } catch (e) {
      last = e.message;
    }
    await sleep(100);
  }
  throw new Error(`release ${version} not healthy after ${timeoutMs} ms (${last})`);
}

export function smoke(L, version, log) {
  const env = ensureEnv(L);
  return runSmoke({ baseUrl: baseUrlOf(env), expectVersion: version, webhookSecret: env.WEBHOOK_SECRET, seedFile: L.seed, log });
}

async function precheckDownstream(env) {
  const failed = [];
  for (const k of ['PAYMENT_URL', 'GIS_URL', 'DOCS_URL', 'NOTIFY_URL']) {
    try {
      const r = await fetch(`${env[k]}/health`, { signal: AbortSignal.timeout(2000) });
      if (!r.ok) failed.push(`${k} HTTP ${r.status}`);
    } catch (e) {
      failed.push(`${k} ${e.message}`);
    }
  }
  if (failed.length) throw new Error(`pre-check failed, nothing changed: ${failed.join('; ')}`);
}

/**
 * Deploy <version>: pre-check, back up, stop, migrate up with the NEW release, switch, start, health,
 * smoke. If smoke fails and there was a previous release, roll back automatically.
 */
export async function deploy(version, { L = layout(), log = console.log, autoRollback = true } = {}) {
  const t0 = Date.now();
  const rel = manifest(version, L);
  const cur = readCurrent(L);
  if (cur?.version === version) throw new Error(`${version} is already live`);
  const env = ensureEnv(L);
  log(`[deploy] ${cur?.version ?? '(none)'} -> ${version} (schema ${rel.schemaVersion})`);
  await precheckDownstream(env);
  await stopApp(L); // stop first so the backup is a consistent snapshot
  const backup = backupStore(L, `pre-deploy-${version}`);
  log(`[deploy] backup: ${backup ?? '(no data yet)'}`);
  const mig = runMigrations(L, version, rel.schemaVersion);
  log(`[deploy] migrate: ${mig.output}`);
  if (!mig.ok) {
    if (backup) copyFileSync(backup, L.store);
    if (cur) {
      startApp(L, cur.version);
      await waitHealthy(L, cur.version);
    }
    history(L, { action: 'deploy', version, ok: false, reason: 'migration_failed' });
    throw new Error(`migration failed, restored backup and restarted ${cur?.version ?? 'nothing'}: ${mig.output}`);
  }
  writeJson(L.current, { version, previous: cur?.version ?? null, backup, deployedAt: new Date().toISOString() });
  startApp(L, version);
  await waitHealthy(L, version);
  const s = await smoke(L, version, (line) => log(`  ${line}`));
  const ms = Date.now() - t0;
  log(`[deploy] smoke ${s.passed}/${s.total} passed, ${s.failed} failed, ${s.skipped} skipped; ${ms} ms`);
  if (s.failed && cur && autoRollback) {
    log('[deploy] smoke failed: rolling back automatically');
    const rb = await rollback({ L, log, reason: 'smoke_failed' });
    history(L, { action: 'deploy', version, ok: false, reason: 'smoke_failed', ms });
    return { ok: false, ms, smoke: s, rolledBack: rb };
  }
  history(L, { action: 'deploy', version, ok: s.failed === 0, ms, smoke: { passed: s.passed, failed: s.failed, skipped: s.skipped } });
  return { ok: s.failed === 0, ms, smoke: s };
}

/**
 * Roll back to the previous release: stop, back up, run the down migration with the CURRENT (newer)
 * release (it is the only one that knows how), fall back to the pre-deploy backup if that fails,
 * switch, start, health, smoke. Timed from the first step to smoke-green.
 */
export async function rollback({ L = layout(), log = console.log, to, reason = 'manual', forceRestore = false } = {}) {
  const t0 = Date.now();
  const cur = readCurrent(L);
  if (!cur) throw new Error('nothing is deployed');
  const target = to ?? cur.previous;
  if (!target) throw new Error(`no previous release recorded for ${cur.version}`);
  const targetRel = manifest(target, L);
  log(`[rollback] ${cur.version} -> ${target} (reason: ${reason})`);
  await stopApp(L);
  const snapshot = backupStore(L, `pre-rollback-from-${cur.version}`);
  let dataPath = 'schema unchanged';
  if (storeSchema(L) > targetRel.schemaVersion) {
    const mig = forceRestore ? { ok: false, output: 'forced restore' } : runMigrations(L, cur.version, targetRel.schemaVersion);
    log(`[rollback] down-migrate with ${cur.version}: ${mig.output}`);
    if (mig.ok) dataPath = 'down-migration (post-upgrade records kept)';
    else if (cur.backup) {
      restoreBackup(L, cur.backup, snapshot);
      dataPath = 'restored pre-deploy backup (post-upgrade records only in the snapshot)';
    } else throw new Error('down migration failed and no pre-deploy backup exists');
  }
  log(`[rollback] data: ${dataPath}; snapshot ${snapshot}`);
  writeJson(L.current, { version: target, previous: null, rolledBackFrom: cur.version, backup: null, deployedAt: new Date().toISOString() });
  startApp(L, target);
  await waitHealthy(L, target);
  const s = await smoke(L, target, (line) => log(`  ${line}`));
  const ms = Date.now() - t0;
  log(`[rollback] smoke ${s.passed}/${s.total} passed, ${s.failed} failed, ${s.skipped} skipped; ${ms} ms`);
  history(L, { action: 'rollback', from: cur.version, to: target, reason, dataPath, ok: s.failed === 0, ms });
  return { ok: s.failed === 0, ms, from: cur.version, to: target, dataPath, smoke: s };
}

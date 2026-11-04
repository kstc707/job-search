// Numbered schema migrations: src/store/migrations/NNN_name.js, each exporting
// { version, description, up(state), down(state) }. A release only ships the migrations up to the
// schema it pins (deploy/package.js), so an older release cannot run a newer migration's down step:
// rollback runs the down migration with the NEWER release before switching back.
import { readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const MIGRATIONS_DIR = join(dirname(fileURLToPath(import.meta.url)), 'migrations');

export async function loadMigrations(dir = MIGRATIONS_DIR) {
  const files = readdirSync(dir).filter((f) => /^\d{3}_[\w-]+\.js$/.test(f)).sort();
  const mods = await Promise.all(files.map((f) => import(pathToFileURL(join(dir, f)).href)));
  return mods.map((m, i) => {
    const version = Number(files[i].slice(0, 3));
    if (m.version !== version) throw new Error(`${files[i]} exports version ${m.version}`);
    return { version, name: files[i], description: m.description, up: m.up, down: m.down };
  });
}

export const latestVersion = (migrations) => migrations.reduce((max, m) => Math.max(max, m.version), 0);

export function migrate(state, target, migrations, now = () => new Date().toISOString()) {
  let s = structuredClone(state);
  s.schemaVersion ??= 0;
  const applied = [];
  const log = (version, direction) => {
    s.migrationLog = [...(s.migrationLog ?? []), { version, direction, at: now() }];
    applied.push(`${direction} ${version}`);
  };
  while (s.schemaVersion < target) {
    const m = migrations.find((x) => x.version === s.schemaVersion + 1);
    if (!m) throw new Error(`No migration to schema ${s.schemaVersion + 1} is available in this release`);
    s = m.up(s);
    s.schemaVersion = m.version;
    log(m.version, 'up');
  }
  while (s.schemaVersion > target) {
    const m = migrations.find((x) => x.version === s.schemaVersion);
    if (!m) throw new Error(`Schema ${s.schemaVersion} is unknown to this release; run its down migration with the release that introduced it`);
    s = m.down(s);
    s.schemaVersion = m.version - 1;
    log(m.version, 'down');
  }
  return { state: s, applied };
}

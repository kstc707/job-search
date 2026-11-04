#!/usr/bin/env node
// node src/store/migrate-cli.js --data <dir> --to <schemaVersion>
// Uses only the migrations packaged with THIS release.
import { existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import { loadMigrations, migrate } from './migrations.js';
import { writeAtomic, readJsonFile } from './fs.js';

const { values } = parseArgs({ options: { data: { type: 'string' }, to: { type: 'string' } } });
if (!values.data || values.to === undefined) {
  console.error('usage: migrate-cli.js --data <dir> --to <schemaVersion>');
  process.exit(64);
}
try {
  const migrations = await loadMigrations();
  mkdirSync(values.data, { recursive: true });
  const file = join(values.data, 'store.json');
  const state = existsSync(file) ? readJsonFile(file) : { schemaVersion: 0 };
  const from = state.schemaVersion ?? 0;
  const { state: next, applied } = migrate(state, Number(values.to), migrations);
  writeAtomic(file, next);
  console.log(JSON.stringify({ from, to: next.schemaVersion, applied }));
} catch (e) {
  console.error(`migration failed: ${e.message}`);
  process.exit(1);
}

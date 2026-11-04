// Single-node JSON file store. All writes go through mutate(): one at a time (a promise queue acts
// as the write lock), applied to a copy of the state, persisted atomically, then swapped in. If the
// mutation throws, nothing is written: that is what makes a failed submit leave the draft untouched.
import { existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { writeAtomic, readJsonFile } from './fs.js';
import { migrate } from './migrations.js';
import { SchemaMismatchError } from '../errors.js';

export class Store {
  constructor(file, state) {
    this.file = file;
    this.state = state;
    this.queue = Promise.resolve();
  }
  /** Current committed state. Treat as read-only. */
  read() {
    return this.state;
  }
  mutate(fn) {
    const run = this.queue.then(async () => {
      const draft = structuredClone(this.state);
      const result = await fn(draft);
      writeAtomic(this.file, draft);
      this.state = draft;
      return result;
    });
    this.queue = run.catch(() => {});
    return run;
  }
}

export async function openStore({ dataDir, codeSchemaVersion, migrations, autoMigrate = false }) {
  mkdirSync(dataDir, { recursive: true });
  const file = join(dataDir, 'store.json');
  let state;
  if (!existsSync(file)) {
    state = migrate({ schemaVersion: 0 }, codeSchemaVersion, migrations).state;
    writeAtomic(file, state);
  } else {
    state = readJsonFile(file);
  }
  if (state.schemaVersion > codeSchemaVersion) {
    throw new SchemaMismatchError(
      `Data store is at schema ${state.schemaVersion} but this release understands schema ${codeSchemaVersion}. ` +
        'Run the down migration with the newer release before starting this one (see RUNBOOK.md, rollback).'
    );
  }
  if (state.schemaVersion < codeSchemaVersion) {
    if (!autoMigrate) {
      throw new SchemaMismatchError(
        `Data store is at schema ${state.schemaVersion}; this release needs ${codeSchemaVersion}. Run migrations first (deploy.js does).`
      );
    }
    state = migrate(state, codeSchemaVersion, migrations).state;
    writeAtomic(file, state);
  }
  return new Store(file, state);
}

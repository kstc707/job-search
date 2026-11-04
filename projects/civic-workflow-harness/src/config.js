import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Root of this checkout or of a packaged release (the directory holding src/, config/, package.json). */
export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'));

export function loadConfig(root = ROOT) {
  return {
    workflow: readJson(join(root, 'config', 'workflow.json')),
    fees: readJson(join(root, 'config', 'fees.json')),
  };
}

/**
 * The release manifest written by deploy/package.js. A dev checkout has none, so it runs as
 * `<package version>-dev` at the newest schema it has migrations for.
 */
export function loadRelease(root, latestSchema) {
  const file = join(root, 'release.json');
  if (existsSync(file)) return readJson(file);
  const pkg = readJson(join(root, 'package.json'));
  return { version: `${pkg.version}-dev`, schemaVersion: latestSchema, builtAt: null };
}

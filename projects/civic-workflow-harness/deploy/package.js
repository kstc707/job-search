#!/usr/bin/env node
// node deploy/package.js <version> [...]   build release artifacts into $DEPLOY_DIR/releases/
import { packageRelease, layout } from './lib.js';

const versions = process.argv.slice(2);
if (!versions.length) {
  console.error('usage: node deploy/package.js <version> [...]   (versions: deploy/releases.json)');
  process.exit(64);
}
for (const v of versions) console.log(JSON.stringify(packageRelease(v, layout())));

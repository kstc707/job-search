import { writeFileSync, renameSync, readFileSync } from 'node:fs';

/** Write to a temp file then rename over the target, so a crash never leaves a half-written store. */
export function writeAtomic(file, data) {
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(data, null, 2));
  renameSync(tmp, file);
}

export const readJsonFile = (file) => JSON.parse(readFileSync(file, 'utf8'));

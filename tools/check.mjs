import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// Run every gate, retain each result, and fail CI if any command fails.
const gates = [
  'format:check',
  'lint',
  'typecheck',
  'python:format:check',
  'python:lint',
  'python:typecheck',
  'python:test',
  'rust:format:check',
  'test:baseline',
  'test:frontend',
  'build',
  'engine:build',
  'engine:smoke',
  'rust:check',
  'rust:lint',
  'rust:test',
  'desktop:build',
  'native:smoke',
  'phase2:smoke',
];

const npmCli = process.env.npm_execpath;
if (!npmCli) {
  throw new Error('Run this quality gate with npm run check.');
}

const results = [];
for (const gate of gates) {
  console.log(`\nRunning ${gate}`);
  const result = spawnSync(process.execPath, [npmCli, 'run', gate], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    stdio: 'inherit',
    shell: false,
  });
  if (result.error) console.error(result.error.message);
  results.push({ gate, result: result.status === 0 ? 'PASS' : 'FAIL' });
}

console.table(results);
process.exitCode = results.some(({ result }) => result === 'FAIL') ? 1 : 0;

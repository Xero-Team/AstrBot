#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const skillRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const repoRoot = path.resolve(skillRoot, '../../..');
const cli = path.join(skillRoot, 'bin/archify.mjs');
const examplesDir = path.join(skillRoot, 'examples');
const typePattern =
  /\.(architecture|workflow|sequence|dataflow|lifecycle)\.json$/;

function run(args) {
  const result = spawnSync(process.execPath, [cli, ...args], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 10 * 60 * 1000,
    maxBuffer: 32 * 1024 * 1024,
  });
  if (result.error) {
    process.stderr.write(`archify ${args.join(' ')} failed: ${result.error.message}\n`);
    process.exit(1);
  }
  if (result.status !== 0) {
    process.stderr.write(result.stderr || result.stdout || '');
    process.exit(result.status || 1);
  }
  return result.stdout;
}

run(['doctor']);

const files = fs
  .readdirSync(examplesDir)
  .filter((name) => typePattern.test(name))
  .sort();
if (files.length === 0) {
  process.stderr.write('no Archify example JSON found\n');
  process.exit(1);
}

for (const name of files) {
  const type = name.match(typePattern)[1];
  const input = path.join(examplesDir, name);
  const receipt = JSON.parse(
    run(['validate', type, input, '--quality', 'showcase', '--json']),
  );
  const checks = Array.isArray(receipt.checks) ? receipt.checks : [];
  const failed = checks.filter((check) => !check.ok);
  if (!receipt.ok || checks.length !== 9 || failed.length > 0) {
    process.stderr.write(`showcase failed: ${name}\n`);
    process.exit(1);
  }
  process.stdout.write(`ok ${name} (${checks.length} checks)\n`);
}

// Semantic identity and references are enforced by the shared loader, not by
// JSON Schema, so the positive examples above cannot prove those failure paths
// stay closed. Derive negative cases from a known-good example and assert the
// diagnostic code the loader is expected to emit.
const negativeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'archify-negative-'));

function expectRejected(type, diagram, expectedCode, label) {
  const input = path.join(negativeDir, `${label}.json`);
  fs.writeFileSync(input, JSON.stringify(diagram));
  const result = spawnSync(
    process.execPath,
    [cli, 'validate', type, input, '--quality', 'showcase', '--json'],
    {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: 10 * 60 * 1000,
      maxBuffer: 32 * 1024 * 1024,
    },
  );
  if (result.error) {
    process.stderr.write(
      `archify ${label} failed: ${result.error.message}\n`,
    );
    process.exit(1);
  }
  if (result.status === 0) {
    process.stderr.write(`negative case was accepted: ${label}\n`);
    process.exit(1);
  }
  let receipt;
  try {
    receipt = JSON.parse(result.stdout);
  } catch {
    process.stderr.write(`negative case emitted no JSON receipt: ${label}\n`);
    process.exit(1);
  }
  const codes = (receipt.diagnostics || []).map((entry) => entry.code);
  if (receipt.ok !== false || !codes.includes(expectedCode)) {
    process.stderr.write(
      `negative case ${label} produced ${JSON.stringify(codes)}, expected ${expectedCode}\n`,
    );
    process.exit(1);
  }
  process.stdout.write(`ok ${label} (${expectedCode})\n`);
}

const baseExample = JSON.parse(
  fs.readFileSync(path.join(examplesDir, 'web-app.architecture.json'), 'utf8'),
);

const duplicateId = structuredClone(baseExample);
duplicateId.components.push({
  ...duplicateId.components[0],
  label: 'Users (duplicate)',
});
expectRejected(
  'architecture',
  duplicateId,
  'semantic/duplicate-id',
  'duplicate-semantic-id',
);

const danglingConnection = structuredClone(baseExample);
danglingConnection.connections[0].to = 'missing-component';
expectRejected(
  'architecture',
  danglingConnection,
  'semantic/unknown-reference',
  'unknown-connection-reference',
);

const danglingBoundary = structuredClone(baseExample);
danglingBoundary.boundaries[0].wraps = [
  ...danglingBoundary.boundaries[0].wraps,
  'missing-component',
];
expectRejected(
  'architecture',
  danglingBoundary,
  'semantic/unknown-reference',
  'unknown-boundary-reference',
);

fs.rmSync(negativeDir, { recursive: true, force: true });

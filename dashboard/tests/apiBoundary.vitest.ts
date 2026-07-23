import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const apiRoot = resolve(process.cwd(), 'src/api');
const forbiddenImport =
  /(?:from\s+|import\s*)['"][^'"]*(?:components|views|composables)(?:\/|['"])/g;

function apiSourceFiles(): string[] {
  return readdirSync(apiRoot, { recursive: true })
    .filter(
      (entry) =>
        entry.endsWith('.ts') &&
        !entry.startsWith('generated/') &&
        !entry.startsWith('generated\\'),
    )
    .map((entry) => resolve(apiRoot, entry));
}

describe('Dashboard API boundary', () => {
  it('keeps API modules independent from presentation and composable layers', () => {
    const violations = apiSourceFiles().flatMap((path) => {
      const source = readFileSync(path, 'utf8');
      return [...source.matchAll(forbiddenImport)].map(
        (match) => `${path}: ${match[0]}`,
      );
    });

    expect(violations).toEqual([]);
  });

  it('uses the v1 directory barrel instead of a legacy monolithic module', () => {
    expect(existsSync(resolve(apiRoot, 'v1/index.ts'))).toBe(true);
    expect(existsSync(resolve(apiRoot, 'v1.ts'))).toBe(false);
  });
});

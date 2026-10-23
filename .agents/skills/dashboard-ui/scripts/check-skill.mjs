#!/usr/bin/env node
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const skillDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(skillDir, '..', '..', '..');
const skillName = 'dashboard-ui';

const errors = [];

function read(path) {
  try {
    return readFileSync(join(repoRoot, path), 'utf8');
  } catch (error) {
    errors.push(`cannot read ${path}: ${error.message}`);
    return '';
  }
}

function readJson(path) {
  const text = read(path);
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (error) {
    errors.push(`cannot parse ${path}: ${error.message}`);
    return {};
  }
}

const skillMd = read('.agents/skills/dashboard-ui/SKILL.md');
const pkg = readJson('dashboard/package.json');

const frontmatter = skillMd.match(/^---\n([\s\S]*?)\n---/);
if (!frontmatter) {
  errors.push('SKILL.md is missing YAML frontmatter');
} else {
  const name = frontmatter[1].match(/^name:\s*(.+)$/m)?.[1]?.trim();
  if (name !== skillName) {
    errors.push(
      `frontmatter name "${name}" does not match directory "${skillName}"`,
    );
  }
  if (!/^description:\s*\S/m.test(frontmatter[1])) {
    errors.push('frontmatter is missing a description');
  }
}

for (const heading of [
  '## Locked',
  '## Open',
  '## Workflow',
  '## Do not',
  '## Handoff',
  '## Verify',
]) {
  if (!skillMd.includes(heading)) {
    errors.push(`SKILL.md is missing heading "${heading}"`);
  }
}

const pinnedDeps = ['vue', 'vuetify', 'pinia', 'vue-router', 'vite', 'vitest'];
for (const dep of pinnedDeps) {
  const version = pkg.dependencies?.[dep] ?? pkg.devDependencies?.[dep];
  if (!version) {
    errors.push(`dashboard/package.json does not declare "${dep}"`);
  } else if (!skillMd.includes(version)) {
    errors.push(
      `SKILL.md does not pin ${dep} ${version}; update the Locked section after a dashboard upgrade`,
    );
  }
}

for (const path of [
  'dashboard/package.json',
  'dashboard/src/design/theme.ts',
  'dashboard/src/plugins/vuetify.ts',
  'dashboard/scripts/check-design-system-source.mjs',
  'dashboard/vitest.config.ts',
  'dashboard/eslint.config.mjs',
  '.agents/skills/dashboard-ui/REFERENCE.md',
]) {
  if (!existsSync(join(repoRoot, path))) {
    errors.push(`referenced path is missing: ${path}`);
  }
}

if (errors.length > 0) {
  console.error(`dashboard-ui skill check failed:\n${errors.join('\n')}`);
  process.exit(1);
}

console.log('dashboard-ui skill check passed');

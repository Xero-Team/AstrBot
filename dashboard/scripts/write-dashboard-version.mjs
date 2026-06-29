import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export function readAstrBotVersion(astrbotInitPath) {
  const source = readFileSync(astrbotInitPath, 'utf8');
  const match = source.match(/^__version__\s*=\s*["']([^"']+)["']/m);
  if (!match) {
    throw new Error(`Unable to read __version__ from ${astrbotInitPath}`);
  }
  return match[1];
}

export function writeDashboardVersionFile({
  astrbotInitPath = resolve(__dirname, '../../astrbot/__init__.py'),
  distDir = resolve(__dirname, '../dist'),
} = {}) {
  const version = `v${readAstrBotVersion(astrbotInitPath)}`;
  const assetsDir = join(distDir, 'assets');
  const versionFile = join(assetsDir, 'version');
  mkdirSync(assetsDir, { recursive: true });
  writeFileSync(versionFile, version, 'utf8');
  return versionFile;
}

function isExecutedDirectly() {
  return process.argv[1] && resolve(process.argv[1]) === __filename;
}

if (isExecutedDirectly()) {
  writeDashboardVersionFile();
}

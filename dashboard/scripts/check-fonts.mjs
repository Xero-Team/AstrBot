import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import {
  collectOtfUnicodeRanges,
  collectUiCharacters,
} from './update-fonts.mjs';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const FONT_ROOT = resolve(__dirname, '..', 'src', 'assets', 'fonts');
const require = createRequire(import.meta.url);
const subsetFontRequire = createRequire(require.resolve('subset-font'));
const { convert } = subsetFontRequire('fontverter');

function sha256(buffer) {
  return createHash('sha256').update(buffer).digest('hex');
}

async function assertFileHash(record) {
  const contents = await readFile(join(FONT_ROOT, record.file));
  if (sha256(contents) !== record.sha256) {
    throw new Error(`Hash mismatch for ${record.file}`);
  }
}

function hasCodePoint(ranges, codePoint) {
  return ranges.some(([start, end]) => start <= codePoint && codePoint <= end);
}

async function assertUiCoverage(file, codePoints) {
  const woff2 = await readFile(join(FONT_ROOT, file));
  const sfnt = await convert(woff2, 'sfnt', 'woff2');
  const ranges = collectOtfUnicodeRanges(sfnt);
  for (const codePoint of codePoints) {
    if (!hasCodePoint(ranges, codePoint)) {
      throw new Error(
        `${file} is missing U+${codePoint.toString(16).toUpperCase()}`,
      );
    }
  }
}

async function unicodeCoverage(file) {
  const woff2 = await readFile(join(FONT_ROOT, file));
  return collectOtfUnicodeRanges(await convert(woff2, 'sfnt', 'woff2'));
}

export async function checkFonts() {
  const metadata = JSON.parse(
    await readFile(join(FONT_ROOT, 'sources.json'), 'utf8'),
  );
  const records = [metadata.generated.css, ...metadata.generated.files];
  await Promise.all(records.map(assertFileHash));

  const notoRanges = (
    await Promise.all(
      metadata.generated.files
        .filter((record) =>
          /astrbot-noto-sans-sc-\d+-regular\.woff2$/.test(record.file),
        )
        .map((record) => unicodeCoverage(record.file)),
    )
  ).flat();
  const expectedCodePoints = new Set(
    (await collectUiCharacters())
      .map((character) => character.codePointAt(0))
      .filter((codePoint) => hasCodePoint(notoRanges, codePoint))
      .map((codePoint) => codePoint.toString(16).toUpperCase()),
  );
  const actualCodePoints = new Set(metadata.generated.uiCodePoints);
  for (const codePoint of expectedCodePoints) {
    if (!actualCodePoints.has(codePoint)) {
      throw new Error(
        `AstrBot UI is missing U+${codePoint}; run pnpm fonts:update`,
      );
    }
  }
  const numericCodePoints = [...expectedCodePoints].map((codePoint) =>
    Number.parseInt(codePoint, 16),
  );
  await Promise.all([
    assertUiCoverage('files/astrbot-ui-regular.woff2', numericCodePoints),
    assertUiCoverage('files/astrbot-ui-bold.woff2', numericCodePoints),
  ]);

  const css = await readFile(join(FONT_ROOT, 'fonts.css'), 'utf8');
  if (/url\(\s*["']?https?:\/\//i.test(css)) {
    throw new Error('Generated font CSS contains a remote URL');
  }
  if (!css.includes('--v-font-body:') || !css.includes('--v-font-heading:')) {
    throw new Error('Generated font CSS is missing Vuetify font variables');
  }
  for (const record of records) await stat(join(FONT_ROOT, record.file));
  console.log(
    `Verified ${records.length} generated font assets without network access.`,
  );
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  checkFonts().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

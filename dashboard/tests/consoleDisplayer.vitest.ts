import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('ConsoleDisplayer log rendering', () => {
  it('batches DOM insertion and keeps log content text-only', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain('document.createDocumentFragment()');
    expect(source).toContain('target.appendChild(fragment)');
    expect(source).toContain('element.textContent = cleanText');
    expect(source).toContain('highlight.textContent = cleanText.slice');
    expect(source).not.toContain('innerHTML = log');
  });

  it('filters logs with a debounced, localized search field', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain("useModuleI18n('features/logs')");
    expect(source).toContain('matchesKeyword(log)');
    expect(source).toContain('searchTimer.value = window.setTimeout');
    expect(source).toContain("tm('search.placeholder')");
  });
});

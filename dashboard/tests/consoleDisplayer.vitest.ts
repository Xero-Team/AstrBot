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
    expect(source).toContain('textContent = log');
    expect(source).not.toContain('innerText = log');
  });
});

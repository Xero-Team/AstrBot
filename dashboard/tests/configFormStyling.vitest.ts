import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

async function source(path: string) {
  return readFile(path, 'utf8');
}

describe('provider configuration form styling', () => {
  it('scopes the shared config-form hooks to config-bearing sections', async () => {
    const body = await source(
      'src/components/provider/ProviderChatCompletionBody.vue',
    );
    expect(body.match(/class="provider-section config-form"/g)).toHaveLength(2);
    expect(body).not.toContain('provider-config-body config-form');

    const page = await source('src/views/ProviderPage.vue');
    expect(page).toContain('class="provider-section config-form"');
    expect(page).not.toContain('provider-config-body config-form');

    for (const file of [
      'src/components/shared/ProviderSelectMenu.vue',
      'src/components/provider/ProviderEditDialog.vue',
    ]) {
      const text = await source(file);
      expect(text, file).toMatch(/<v-card-text[^>]*class="[^"]*config-form/);
      expect(text, file).toContain('@/styles/config-form.css');
    }
  });
});

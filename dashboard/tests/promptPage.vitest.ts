import { describe, expect, it, vi } from 'vitest';
import PromptPage from '@/views/PromptPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/views/prompt', () => ({
  PromptManager: {
    name: 'PromptManager',
    template: '<div data-testid="prompt-manager"></div>',
  },
}));

describe('PromptPage', () => {
  it('renders the prompt heading and manager', () => {
    const wrapper = mountWithVuetify(PromptPage);

    expect(wrapper.get('h1').text().length).toBeGreaterThan(0);
    expect(wrapper.get('.config-docs-link').attributes('href')).toBe(
      '/help/en/use/prompt.html',
    );
    expect(wrapper.get('[data-testid="prompt-manager"]').exists()).toBe(true);
  });
});

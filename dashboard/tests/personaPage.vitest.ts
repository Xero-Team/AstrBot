import { describe, expect, it, vi } from 'vitest';
import PersonaPage from '@/views/PersonaPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/views/persona', () => ({
  PersonaManager: {
    name: 'PersonaManager',
    template: '<div data-testid="persona-manager"></div>',
  },
}));

describe('PersonaPage', () => {
  it('renders the persona heading and manager', () => {
    const wrapper = mountWithVuetify(PersonaPage);

    expect(wrapper.get('h1').text().length).toBeGreaterThan(0);
    expect(wrapper.get('.config-docs-link').attributes('href')).toBe(
      '/help/en/use/persona.html',
    );
    expect(wrapper.get('[data-testid="persona-manager"]').exists()).toBe(true);
  });
});

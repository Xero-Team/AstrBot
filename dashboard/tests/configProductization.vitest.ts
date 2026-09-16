import { describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ConfigProfileMenu from '@/components/config/ConfigProfileMenu.vue';
import ProviderSelectMenu from '@/components/shared/ProviderSelectMenu.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/utils/toast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

vi.mock('@/api/v1', () => ({
  providerApi: {
    listByProviderType: vi.fn(async () => ({
      data: {
        status: 'ok',
        model_metadata: {},
        data: [
          {
            id: 'openai-gpt',
            type: 'openai_chat_completion',
            provider_source_id: 'openai',
            model: 'gpt-4o',
            api_base: 'https://api.openai.com/v1',
            enable: true,
          },
          {
            id: 'claude',
            type: 'anthropic_chat_completion',
            provider_source_id: 'anthropic',
            model: 'claude-sonnet',
            api_base: 'https://api.anthropic.com',
            enable: true,
          },
        ],
      },
    })),
    test: vi.fn(),
  },
}));

describe('configuration productization controls', () => {
  it('shows the configured profile name and emits profile selection', async () => {
    const wrapper = mountWithVuetify(ConfigProfileMenu, {
      props: {
        modelValue: 'profile-1',
        items: [
          { id: 'default', name: 'Default' },
          { id: 'profile-1', name: 'Production' },
        ],
      },
    });

    expect(wrapper.find('.config-profile-trigger__title').text()).toBe(
      'Production',
    );

    await wrapper.find('.config-profile-trigger').trigger('click');
    const profileItems = document.body.querySelectorAll(
      '.config-profile-menu__item',
    );
    expect(profileItems).toHaveLength(2);
    await (profileItems[0] as HTMLElement).click();

    expect(wrapper.emitted('select')?.[0]).toEqual(['default']);
  });

  it('uses the stored model name for the chat input trigger', () => {
    const wrapper = mountWithVuetify(ProviderSelectMenu, {
      props: {
        modelValue: 'provider-1',
        fallbackModel: 'gpt-4o',
        variant: 'input',
      },
    });

    expect(wrapper.find('.provider-trigger-title').text()).toBe('gpt-4o');
  });

  it('honors a custom trigger label for config selectors', () => {
    const wrapper = mountWithVuetify(ProviderSelectMenu, {
      props: {
        variant: 'config',
        buttonText: 'Select provider pool',
      },
    });

    expect(wrapper.find('.provider-trigger-title').text()).toBe(
      'Select provider pool',
    );
  });

  it('groups models by source and shows a source filter', async () => {
    const wrapper = mountWithVuetify(ProviderSelectMenu, {
      props: {
        modelValue: 'openai-gpt',
        variant: 'header',
      },
    });

    await wrapper.find('.provider-trigger').trigger('click');
    await flushPromises();

    expect(
      document.body.querySelector('.provider-source-trigger'),
    ).not.toBeNull();
    const headers = [
      ...document.body.querySelectorAll('.provider-source-header'),
    ].map((node) => node.textContent?.trim());
    expect(headers).toEqual(expect.arrayContaining(['openai', 'anthropic']));
    expect(
      document.body.querySelectorAll('.provider-menu-item').length,
    ).toBeGreaterThan(1);
  });
});

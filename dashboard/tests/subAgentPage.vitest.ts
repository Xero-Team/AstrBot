import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SubAgentPage from '@/views/SubAgentPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  getConfig: vi.fn(),
  updateConfig: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  subagentApi: api,
}));

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn(),
}));

vi.mock('@/components/shared/PromptQuickPreview.vue', () => ({
  default: { template: '<div class="prompt-preview-stub"></div>' },
}));

vi.mock('@/components/shared/PromptSelector.vue', () => ({
  default: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="prompt-selector-stub"></div>',
  },
}));

vi.mock('@/components/shared/ProviderSelector.vue', () => ({
  default: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="provider-selector-stub"></div>',
  },
}));

vi.mock('@/utils/confirmDialog', () => ({
  askForConfirmation: vi.fn(),
  useConfirmDialog: () => undefined,
}));

function apiResponse(data: unknown) {
  return { data: { status: 'ok', data } };
}

describe('SubAgentPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizes loaded agent data and blocks an invalid save before sending it to the API', async () => {
    api.getConfig.mockResolvedValue(
      apiResponse({
        main_enable: true,
        remove_main_duplicate_tools: true,
        agents: [
          {
            name: 123,
            prompt_id: null,
            public_description: null,
            enabled: undefined,
          },
        ],
      }),
    );
    const removeListenerSpy = vi.spyOn(window, 'removeEventListener');
    const wrapper = mountWithVuetify(SubAgentPage);
    await flushPromises();

    expect(wrapper.text()).toContain('123');
    expect(wrapper.text()).toContain('Enabled');

    const saveButton = wrapper
      .findAll('button')
      .find((button) => button.text().trim() === 'Save');
    expect(saveButton).toBeDefined();
    await saveButton!.trigger('click');
    await flushPromises();

    expect(api.updateConfig).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain(
      'Invalid SubAgent name: only lowercase letters/numbers/underscores, starting with a letter',
    );

    wrapper.unmount();
    expect(removeListenerSpy).toHaveBeenCalledWith(
      'beforeunload',
      expect.any(Function),
    );
  });

  it('uses a stable load failure message when the transport exception is sensitive', async () => {
    api.getConfig.mockRejectedValue(
      new Error('api_key=subagent-secret at http://internal.example/config'),
    );
    const wrapper = mountWithVuetify(SubAgentPage);
    await flushPromises();

    expect(document.body.textContent).toContain('Failed to load config');
    expect(document.body.textContent).not.toContain('subagent-secret');
    expect(document.body.textContent).not.toContain('internal.example');

    wrapper.unmount();
  });
});

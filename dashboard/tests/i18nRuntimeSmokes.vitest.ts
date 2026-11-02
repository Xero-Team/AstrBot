import { ref } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { initI18n } from '@/i18n/composables';
import { useProviderModelConfigDialog } from '@/composables/useProviderModelConfigDialog';
import ObjectEditor from '@/components/shared/ObjectEditor.vue';
import TemplateListEditor from '@/components/shared/TemplateListEditor.vue';
import PromptSelector from '@/components/shared/PromptSelector.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@/api/v1', () => ({
  promptApi: {
    tree: vi.fn(async () => ({
      data: {
        status: 'ok',
        data: [],
      },
    })),
    list: vi.fn(async () => ({
      data: {
        status: 'ok',
        data: [],
      },
    })),
  },
}));

describe('i18n runtime smokes', () => {
  beforeEach(async () => {
    await initI18n('en-US');
  });

  afterEach(async () => {
    await initI18n('en-US');
  });

  it('renders TemplateListEditor in en-US without missing expand/collapse warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    mountWithVuetify(TemplateListEditor, {
      props: {
        modelValue: [
          {
            __template_key: 'preset',
            title: 'Entry',
          },
        ],
        templateSchema: {
          preset: {
            description: 'Preset',
            items: {},
          },
        },
      },
      global: {
        stubs: {
          ConfigItemRenderer: {
            template: '<div class="config-item-renderer-stub"></div>',
          },
        },
      },
    });

    await flushPromises();

    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes('Translation key not found: core.common.expand'),
        ),
      ),
    ).toBe(false);
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes(
            'Translation key not found: core.common.collapse',
          ),
        ),
      ),
    ).toBe(false);
  });

  it('resolves PromptSelector edit label in en-US without missing-key warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(PromptSelector, {
      props: {
        modelValue: '',
      },
      global: {
        stubs: {
          BaseFolderItemSelector: {
            props: ['labels'],
            template:
              '<div class="prompt-selector-stub">{{ labels.editButton }}</div>',
          },
          PromptForm: {
            template: '<div class="prompt-form-stub"></div>',
          },
        },
      },
    });

    await flushPromises();

    expect(wrapper.find('.prompt-selector-stub').text()).toBe(
      'Edit current prompt',
    );
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes(
            'Translation key not found: core.shared.promptSelector.editPrompt',
          ),
        ),
      ),
    ).toBe(false);
  });

  it('renders the Gemini custom_extra_body template in en-US', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const dialog = useProviderModelConfigDialog({
      selectedProviderSource: ref({
        id: 'gemini',
        type: 'googlegenai_chat_completion',
      }),
      configSchema: ref({
        provider: {
          items: {
            id: {},
            model: {},
            custom_extra_body: { template_schema: {} },
          },
        },
      }),
      buildModelProviderConfig: () => ({ id: 'm', model: 'm' }),
      loadConfig: vi.fn(),
      tm: (key) => key,
      showMessage: vi.fn(),
    });
    const extraBody =
      dialog.providerModelConfigSchema.value.provider.items.custom_extra_body;

    const wrapper = mountWithVuetify(ObjectEditor, {
      props: {
        modelValue: {},
        itemMeta: extraBody,
        configKey: 'provider_group.provider.custom_extra_body',
      },
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div v-if="modelValue"><slot /></div>',
          },
        },
      },
    });
    await wrapper.find('button').trigger('click');
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain('Max Output Tokens');
    expect(text).toContain('Maximum number of generated tokens.');
    expect(text).not.toMatch(/[\u4e00-\u9fff]/);
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) => String(arg).includes('Translation key not found')),
      ),
    ).toBe(false);
  });
});

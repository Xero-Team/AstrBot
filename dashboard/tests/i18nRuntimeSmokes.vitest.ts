import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { initI18n } from '@/i18n/composables';
import TemplateListEditor from '@/components/shared/TemplateListEditor.vue';
import PersonaSelector from '@/components/shared/PersonaSelector.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@/api/v1', () => ({
  personaApi: {
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

  it('resolves PersonaSelector edit label in en-US without missing-key warnings', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(PersonaSelector, {
      props: {
        modelValue: '',
      },
      global: {
        stubs: {
          BaseFolderItemSelector: {
            props: ['labels'],
            template:
              '<div class="persona-selector-stub">{{ labels.editButton }}</div>',
          },
          PersonaForm: {
            template: '<div class="persona-form-stub"></div>',
          },
        },
      },
    });

    await flushPromises();

    expect(wrapper.find('.persona-selector-stub').text()).toBe(
      'Edit current persona',
    );
    expect(
      warnSpy.mock.calls.some((args) =>
        args.some((arg) =>
          String(arg).includes(
            'Translation key not found: core.shared.personaSelector.editPersona',
          ),
        ),
      ),
    ).toBe(false);
  });
});

import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BtwPage from '@/views/BtwPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  listMock: vi.fn(),
  getProfileMock: vi.fn(),
  updateProfileMock: vi.fn(),
  stepUpMock: vi.fn(),
}));

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: {
    name: 'VueMonacoEditor',
    template: '<div class="monaco-editor-stub"></div>',
  },
}));

vi.mock('@/api/v1', () => ({
  configProfileApi: {
    list: testState.listMock,
    get: testState.getProfileMock,
    update: testState.updateProfileMock,
  },
}));

vi.mock('@/api/v1/authorization', () => ({
  STEP_UP_TTL_SECONDS: 300,
  authorizationApi: {
    stepUp: testState.stepUpMock,
    webChatStepUp: vi.fn(),
  },
}));

/** The metadata shape the config endpoints return for the BTW section. */
const METADATA = {
  ai_group: {
    metadata: {
      btw: {
        description: 'BTW 双循环',
        type: 'object',
        items: {
          'btw.enabled': {
            description: 'Enable BTW',
            type: 'bool',
            hint: 'Experimental.',
          },
        },
      },
    },
  },
};

const CONFIG = { btw: { enabled: false } };

function mountPage() {
  return mountWithVuetify(BtwPage);
}

describe('BtwPage', () => {
  beforeEach(() => {
    testState.listMock.mockResolvedValue({
      data: { status: 'ok', data: { info_list: [] } },
    });
    testState.getProfileMock.mockResolvedValue({
      data: { status: 'ok', data: { config: CONFIG, metadata: METADATA } },
    });
    testState.updateProfileMock.mockResolvedValue({
      data: { status: 'ok', message: 'saved' },
    });
  });

  it('loads through the profile endpoint and renders the BTW settings', async () => {
    // Not the system-config endpoint: that one serves the system metadata
    // tree alone, so the AI section holding `btw` would be missing and the
    // page would report nothing to edit.
    const wrapper = mountPage();
    await flushPromises();

    expect(testState.getProfileMock).toHaveBeenCalledWith('default');
    expect(wrapper.text()).toContain('BTW');
    // The group renders through the shared config renderer, so the settings
    // themselves are the ones the config file page used to show.
    expect(wrapper.find('.config-item-renderer, .v-input').exists()).toBe(true);
    wrapper.unmount();
  });

  it('reports a load failure instead of rendering an empty form', async () => {
    testState.getProfileMock.mockRejectedValue(new Error('nope'));

    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain('Could not load the BTW settings');
    wrapper.unmount();
  });

  it('saves the edited value back to the system profile', async () => {
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.find('.btw-page__save').trigger('click');
    await flushPromises();

    expect(testState.updateProfileMock).toHaveBeenCalledWith(
      'default',
      CONFIG,
      expect.objectContaining({ headers: {} }),
    );
    wrapper.unmount();
  });

  it('offers the named profiles alongside the default one', async () => {
    testState.listMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          info_list: [
            { id: 'default', name: 'Default' },
            { id: 'work', name: 'Work profile' },
          ],
        },
      },
    });

    const wrapper = mountPage();
    await flushPromises();

    const select = wrapper.findComponent('.btw-page__scope-select');
    expect(select.exists()).toBe(true);
    const values = (select.props('items') as { value: string }[]).map(
      (item) => item.value,
    );
    expect(values).toEqual(['default', 'work']);
    wrapper.unmount();
  });
});

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

/**
 * The save/discard/stay prompt, under test control.
 *
 * It is stubbed rather than driven through the DOM because the real one renders
 * inside a teleported dialog, and what matters here is which way the page goes
 * for each answer.
 */
const dialogControl = vi.hoisted(() => ({
  answer: false as boolean | 'close',
  asked: false,
}));

vi.mock('@/components/config/UnsavedChangesConfirmDialog.vue', () => ({
  default: {
    name: 'UnsavedChangesConfirmDialog',
    setup(_props: unknown, { expose }: { expose: (api: object) => void }) {
      expose({
        open: () => {
          dialogControl.asked = true;
          return Promise.resolve(dialogControl.answer);
        },
      });
      return () => null;
    },
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
    dialogControl.answer = false;
    dialogControl.asked = false;
    CONFIG.btw.enabled = false;
    testState.listMock.mockReset();
    testState.getProfileMock.mockReset();
    testState.updateProfileMock.mockReset();
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

  it('switches profiles without asking when there is nothing unsaved', async () => {
    testState.listMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: { info_list: [{ id: 'work', name: 'Work' }] },
      },
    });

    const wrapper = mountPage();
    await flushPromises();
    await switchScope(wrapper, 'work');

    expect(dialogControl.asked).toBe(false);
    expect(testState.getProfileMock).toHaveBeenLastCalledWith('work');
    wrapper.unmount();
  });

  it('stays on the profile being edited when the prompt is closed', async () => {
    testState.listMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: { info_list: [{ id: 'work', name: 'Work' }] },
      },
    });
    dialogControl.answer = 'close';

    const wrapper = mountPage();
    await flushPromises();
    CONFIG.btw.enabled = true;
    await switchScope(wrapper, 'work');

    expect(dialogControl.asked).toBe(true);
    // The select is bound one way, so closing the prompt leaves it where it
    // was rather than needing the page to undo the move v-model would have made.
    expect(scopeValue(wrapper)).toBe('default');
    expect(testState.updateProfileMock).not.toHaveBeenCalled();
    expect(testState.getProfileMock).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it('switches and discards when the prompt is cancelled', async () => {
    // The dialog spells this out: its cancel button is "discard and switch".
    // The safer outcome, staying, is closing the prompt.
    testState.listMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: { info_list: [{ id: 'work', name: 'Work' }] },
      },
    });
    dialogControl.answer = false;

    const wrapper = mountPage();
    await flushPromises();
    CONFIG.btw.enabled = true;
    await switchScope(wrapper, 'work');

    expect(testState.updateProfileMock).not.toHaveBeenCalled();
    expect(testState.getProfileMock).toHaveBeenLastCalledWith('work');
    wrapper.unmount();
  });

  it('saves the profile it is leaving before switching away from it', async () => {
    testState.listMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: { info_list: [{ id: 'work', name: 'Work' }] },
      },
    });
    dialogControl.answer = true;

    const wrapper = mountPage();
    await flushPromises();
    CONFIG.btw.enabled = true;
    await switchScope(wrapper, 'work');

    expect(testState.updateProfileMock).toHaveBeenCalledWith(
      'default',
      CONFIG,
      expect.objectContaining({ headers: {} }),
    );
    expect(testState.getProfileMock).toHaveBeenLastCalledWith('work');
    wrapper.unmount();
  });

  it('stays put when the profile it is leaving cannot be saved', async () => {
    testState.listMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: { info_list: [{ id: 'work', name: 'Work' }] },
      },
    });
    testState.updateProfileMock.mockResolvedValue({
      data: { status: 'error', message: 'no' },
    });
    dialogControl.answer = true;

    const wrapper = mountPage();
    await flushPromises();
    CONFIG.btw.enabled = true;
    await switchScope(wrapper, 'work');

    expect(scopeValue(wrapper)).toBe('default');
    expect(testState.getProfileMock).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });
});

/** Move the profile select the way Vuetify would, without the DOM behind it. */
async function switchScope(
  wrapper: ReturnType<typeof mountPage>,
  value: string,
) {
  await wrapper
    .findComponent('.btw-page__scope-select')
    .vm.$emit('update:model-value', value);
  await flushPromises();
}

function scopeValue(wrapper: ReturnType<typeof mountPage>) {
  return wrapper.findComponent('.btw-page__scope-select').props('modelValue');
}

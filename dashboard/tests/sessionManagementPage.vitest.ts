import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SessionManagementPage from '@/views/SessionManagementPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  listRules: vi.fn(),
  activeUmos: vi.fn(),
  upsertRule: vi.fn(),
  deleteRules: vi.fn(),
  batchUpdateProvider: vi.fn(),
  batchUpdateService: vi.fn(),
  listGroups: vi.fn(),
  createGroup: vi.fn(),
  updateGroup: vi.fn(),
  deleteGroup: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  sessionApi: api,
}));

vi.mock('@/components/shared/UmoDisplay.vue', () => ({
  default: {
    template: '<span class="umo-display-stub"></span>',
  },
}));

vi.mock('@/utils/confirmDialog', () => ({
  askForConfirmation: vi.fn(),
  useConfirmDialog: () => undefined,
}));

vi.mock('@/utils/platformUtils', () => ({
  getPlatformColor: () => 'primary',
}));

const dataTableStub = {
  props: ['items'],
  template: `<div class="session-table-stub">
    <div
      v-for="item in items"
      :key="item.sender_id || item.umo"
      class="session-table-row"
    >
      <slot name="item.rules_overview" :item="item" />
      <slot name="item.actions" :item="item" />
    </div>
    <slot name="no-data" />
  </div>`,
};

function senderRuleResponse(item: unknown) {
  return response({
    rules: [item],
    total: 1,
    available_personas: [],
    available_chat_providers: [],
    available_stt_providers: [],
    available_tts_providers: [],
    available_plugins: [],
    available_kbs: [],
  });
}

async function switchToSender(wrapper: ReturnType<typeof mountWithVuetify>) {
  const senderToggle = wrapper
    .findAll('button')
    .find((button) => button.text() === 'Sender');
  expect(senderToggle).toBeDefined();
  await senderToggle!.trigger('click');
  await flushPromises();
}

function findSaveButton(wrapper: ReturnType<typeof mountWithVuetify>) {
  const save = wrapper
    .findAllComponents({ name: 'VBtn' })
    .find((button) => button.text() === 'Save');
  expect(save).toBeDefined();
  return save!;
}

function setSenderLlmMode(
  wrapper: ReturnType<typeof mountWithVuetify>,
  value: string,
) {
  const select = wrapper
    .findAllComponents({ name: 'VSelect' })
    .find((component) => component.props('label') === 'LLM');
  expect(select).toBeDefined();
  select!.vm.$emit('update:modelValue', value);
}

function response(data: unknown) {
  return { data: { status: 'ok', data } };
}

describe('SessionManagementPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listGroups.mockResolvedValue(response({ groups: [] }));
    api.activeUmos.mockResolvedValue(response({ umos: [], umo_infos: [] }));
    api.listRules.mockResolvedValue(
      response({
        rules: [],
        total: 0,
        available_personas: [{ name: 'persona-a' }],
        available_chat_providers: [],
        available_stt_providers: [],
        available_tts_providers: [],
        available_plugins: [],
        available_kbs: [],
      }),
    );
    api.upsertRule.mockResolvedValue(response({}));
  });

  it('does not expose a sensitive transport failure while loading session rules', async () => {
    api.listRules.mockRejectedValue(
      new Error('Bearer session-secret at http://internal.example/sessions'),
    );
    const wrapper = mountWithVuetify(SessionManagementPage, {
      global: {
        stubs: { VDataTableServer: dataTableStub },
      },
    });
    await flushPromises();

    expect(document.body.textContent).toContain('Failed to load data');
    expect(document.body.textContent).not.toContain('session-secret');
    expect(document.body.textContent).not.toContain('internal.example');

    wrapper.unmount();
  });

  it('keeps an explicit business validation message from the session API', async () => {
    api.listRules.mockResolvedValue({
      data: {
        status: 'error',
        message: 'A custom group must contain at least one session',
      },
    });
    const wrapper = mountWithVuetify(SessionManagementPage, {
      global: {
        stubs: { VDataTableServer: dataTableStub },
      },
    });
    await flushPromises();

    expect(document.body.textContent).toContain(
      'A custom group must contain at least one session',
    );

    wrapper.unmount();
  });

  it('saves only fields the operator set on a new sender rule', async () => {
    const wrapper = mountWithVuetify(SessionManagementPage, {
      global: {
        stubs: { VDataTableServer: dataTableStub },
      },
    });
    await flushPromises();
    expect(api.listRules).toHaveBeenCalledWith(
      expect.objectContaining({ target_type: 'session' }),
    );

    await switchToSender(wrapper);
    expect(api.listRules).toHaveBeenCalledWith(
      expect.objectContaining({ target_type: 'sender' }),
    );

    const addRule = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Add Rule');
    expect(addRule).toBeDefined();
    await addRule!.trigger('click');
    await flushPromises();

    const senderField = wrapper
      .findAllComponents({ name: 'VTextField' })
      .find((field) => field.props('label') === 'Sender subject ID');
    expect(senderField).toBeDefined();
    const next = wrapper
      .findAllComponents({ name: 'VBtn' })
      .find((button) => button.text() === 'Next');
    expect(next).toBeDefined();

    await senderField!.setValue('99');
    await flushPromises();
    expect(next!.attributes('disabled')).toBeDefined();

    await senderField!.setValue('im:napcat:bot:99');
    await flushPromises();
    expect(next!.attributes('disabled')).toBeUndefined();
    await next!.trigger('click');
    await flushPromises();

    expect(document.body.textContent).toContain('Block this sender');
    expect(document.body.textContent).not.toContain('Persona Configuration');
    expect(document.body.textContent).not.toContain('Plugin Configuration');
    expect(document.body.textContent).not.toContain(
      'Knowledge Base Configuration',
    );
    expect(document.body.textContent).not.toContain('Provider Configuration');

    await findSaveButton(wrapper).trigger('click');
    await flushPromises();
    expect(api.upsertRule).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('No changes to save');

    setSenderLlmMode(wrapper, 'true');
    await wrapper.vm.$nextTick();
    await findSaveButton(wrapper).trigger('click');
    await flushPromises();

    expect(api.upsertRule).toHaveBeenCalledWith({
      target_type: 'sender',
      sender_id: 'im:napcat:bot:99',
      rule_key: 'session_service_config',
      rule_value: {
        llm_enabled: true,
      },
    });

    wrapper.unmount();
  });

  it('clears a written sender llm back to follow session', async () => {
    api.listRules.mockImplementation(
      async (params: { target_type?: string } = {}) =>
        params.target_type === 'sender'
          ? senderRuleResponse({
              target_type: 'sender',
              sender_id: 'im:napcat:bot:99',
              rules: {
                session_service_config: { blocked: true, llm_enabled: true },
              },
            })
          : response({ rules: [], total: 0 }),
    );

    const wrapper = mountWithVuetify(SessionManagementPage, {
      global: {
        stubs: { VDataTableServer: dataTableStub },
      },
    });
    await flushPromises();
    await switchToSender(wrapper);
    expect(wrapper.text()).toContain('LLM');

    const edit = wrapper
      .findAll('button')
      .find((button) => button.attributes('aria-label') === 'Edit Rules');
    expect(edit).toBeDefined();
    await edit!.trigger('click');
    await flushPromises();

    setSenderLlmMode(wrapper, '__astrbot_follow_session__');
    await wrapper.vm.$nextTick();
    await findSaveButton(wrapper).trigger('click');
    await flushPromises();

    expect(api.upsertRule).toHaveBeenCalledWith({
      target_type: 'sender',
      sender_id: 'im:napcat:bot:99',
      rule_key: 'session_service_config',
      rule_value: {
        blocked: true,
        llm_enabled: null,
      },
    });

    wrapper.unmount();
  });

  it('keeps a blocked-only sender rule from fabricating an llm value', async () => {
    api.listRules.mockImplementation(
      async (params: { target_type?: string } = {}) =>
        params.target_type === 'sender'
          ? senderRuleResponse({
              target_type: 'sender',
              sender_id: 'im:napcat:bot:99',
              rules: {
                session_service_config: { blocked: true },
              },
            })
          : response({ rules: [], total: 0 }),
    );

    const wrapper = mountWithVuetify(SessionManagementPage, {
      global: {
        stubs: { VDataTableServer: dataTableStub },
      },
    });
    await flushPromises();
    await switchToSender(wrapper);
    expect(wrapper.text()).not.toContain('LLM');

    const edit = wrapper
      .findAll('button')
      .find((button) => button.attributes('aria-label') === 'Edit Rules');
    expect(edit).toBeDefined();
    await edit!.trigger('click');
    await flushPromises();
    await findSaveButton(wrapper).trigger('click');
    await flushPromises();

    expect(api.upsertRule).toHaveBeenCalledWith({
      target_type: 'sender',
      sender_id: 'im:napcat:bot:99',
      rule_key: 'session_service_config',
      rule_value: {
        blocked: true,
      },
    });

    wrapper.unmount();
  });

  it('leaves an explicit blocked false untouched on save', async () => {
    api.listRules.mockImplementation(
      async (params: { target_type?: string } = {}) =>
        params.target_type === 'sender'
          ? senderRuleResponse({
              target_type: 'sender',
              sender_id: 'im:napcat:bot:99',
              rules: {
                session_service_config: { blocked: false },
              },
            })
          : response({ rules: [], total: 0 }),
    );

    const wrapper = mountWithVuetify(SessionManagementPage, {
      global: {
        stubs: { VDataTableServer: dataTableStub },
      },
    });
    await flushPromises();
    await switchToSender(wrapper);

    const edit = wrapper
      .findAll('button')
      .find((button) => button.attributes('aria-label') === 'Edit Rules');
    expect(edit).toBeDefined();
    await edit!.trigger('click');
    await flushPromises();
    await findSaveButton(wrapper).trigger('click');
    await flushPromises();

    expect(api.upsertRule).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('No changes to save');

    wrapper.unmount();
  });

  it('defaults unwritten IM session services off and WebChat on', async () => {
    api.activeUmos.mockResolvedValue(
      response({
        umos: [
          'napcat:GroupMessage:room-a',
          'webchat:FriendMessage:webchat!u!c',
        ],
        umo_infos: [],
      }),
    );

    async function openNewSessionRule(umo: string) {
      const wrapper = mountWithVuetify(SessionManagementPage, {
        global: {
          stubs: { VDataTableServer: dataTableStub },
        },
      });
      await flushPromises();
      const addRule = wrapper
        .findAll('button')
        .find((button) => button.text() === 'Add Rule');
      expect(addRule).toBeDefined();
      await addRule!.trigger('click');
      await flushPromises();
      const umoField = wrapper
        .findAllComponents({ name: 'VAutocomplete' })
        .find((field) => field.props('label') === 'Select Session');
      expect(umoField).toBeDefined();
      await umoField!.setValue(umo);
      await flushPromises();
      const next = wrapper
        .findAllComponents({ name: 'VBtn' })
        .find((button) => button.text() === 'Next');
      expect(next).toBeDefined();
      await next!.trigger('click');
      await flushPromises();
      return wrapper;
    }

    function checkboxValue(
      wrapper: ReturnType<typeof mountWithVuetify>,
      label: string,
    ) {
      return wrapper
        .findAllComponents({ name: 'VCheckbox' })
        .find((box) => box.props('label') === label)
        ?.props('modelValue');
    }

    const imWrapper = await openNewSessionRule('napcat:GroupMessage:room-a');
    expect(checkboxValue(imWrapper, 'Enable Session')).toBe(false);
    expect(checkboxValue(imWrapper, 'Enable LLM')).toBe(false);
    expect(checkboxValue(imWrapper, 'Enable TTS')).toBe(false);
    const imSave = imWrapper
      .findAllComponents({ name: 'VBtn' })
      .find((button) => button.text() === 'Save');
    expect(imSave).toBeDefined();
    await imSave!.trigger('click');
    await flushPromises();
    expect(api.upsertRule).toHaveBeenCalledWith({
      umo: 'napcat:GroupMessage:room-a',
      rule_key: 'session_service_config',
      rule_value: {
        session_enabled: false,
        llm_enabled: false,
        tts_enabled: false,
        session_blocked: false,
        custom_name: '',
      },
    });
    imWrapper.unmount();

    api.upsertRule.mockClear();
    const webchatWrapper = await openNewSessionRule(
      'webchat:FriendMessage:webchat!u!c',
    );
    expect(checkboxValue(webchatWrapper, 'Enable Session')).toBe(true);
    expect(checkboxValue(webchatWrapper, 'Enable LLM')).toBe(true);
    expect(checkboxValue(webchatWrapper, 'Enable TTS')).toBe(true);
    const webchatSave = webchatWrapper
      .findAllComponents({ name: 'VBtn' })
      .find((button) => button.text() === 'Save');
    expect(webchatSave).toBeDefined();
    await webchatSave!.trigger('click');
    await flushPromises();
    expect(api.upsertRule).toHaveBeenCalledWith({
      umo: 'webchat:FriendMessage:webchat!u!c',
      rule_key: 'session_service_config',
      rule_value: {
        session_enabled: true,
        llm_enabled: true,
        tts_enabled: true,
        session_blocked: false,
        custom_name: '',
      },
    });
    webchatWrapper.unmount();
  });
});

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
  template: '<div class="session-table-stub"><slot name="no-data" /></div>',
};

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

  it('loads sender overlays and saves only blocked and llm fields', async () => {
    const wrapper = mountWithVuetify(SessionManagementPage, {
      global: {
        stubs: { VDataTableServer: dataTableStub },
      },
    });
    await flushPromises();
    expect(api.listRules).toHaveBeenCalledWith(
      expect.objectContaining({ target_type: 'session' }),
    );

    const senderToggle = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Sender');
    expect(senderToggle).toBeDefined();
    await senderToggle!.trigger('click');
    await flushPromises();
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
    await senderField!.setValue('im:napcat:bot:99');
    await flushPromises();

    const next = wrapper
      .findAllComponents({ name: 'VBtn' })
      .find((button) => button.text() === 'Next');
    expect(next).toBeDefined();
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

    const save = wrapper
      .findAllComponents({ name: 'VBtn' })
      .find((button) => button.text() === 'Save');
    expect(save).toBeDefined();
    await save!.trigger('click');
    await flushPromises();

    expect(api.upsertRule).toHaveBeenCalledWith({
      target_type: 'sender',
      sender_id: 'im:napcat:bot:99',
      rule_key: 'session_service_config',
      rule_value: {
        blocked: false,
        llm_enabled: true,
      },
    });

    wrapper.unmount();
  });
});

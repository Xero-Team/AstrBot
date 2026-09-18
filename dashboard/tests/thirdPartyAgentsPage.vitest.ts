import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardTwoFactorDialog from '@/components/shared/DashboardTwoFactorDialog.vue';
import ThirdPartyAgentsPage from '@/views/ThirdPartyAgentsPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  getProfileMock: vi.fn(),
  updateProfileMock: vi.fn(),
  cliStateMock: vi.fn(),
  switchMock: vi.fn(),
  removeMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  codingCliApi: {
    state: testState.cliStateMock,
    switchProvider: testState.switchMock,
    remove: testState.removeMock,
  },
  configProfileApi: {
    get: testState.getProfileMock,
    update: testState.updateProfileMock,
  },
}));

vi.mock('@/api/v1/authorization', () => ({
  STEP_UP_TTL_SECONDS: 300,
  authorizationApi: {
    stepUp: vi.fn(),
    webChatStepUp: vi.fn(),
  },
}));

/**
 * A profile as the endpoint returns it.
 *
 * The key is the marker a response carries, not the key: the redaction happens
 * before the page ever sees it, and a fixture that carries a real secret tests
 * a path that does not exist.
 *
 * Built fresh for every test: the page edits the configuration it was handed,
 * so a shared object would carry one test's edits into the next.
 */
function configFixture() {
  return {
    btw: {
      cli_providers: [
        {
          id: 'gw',
          name: 'Gateway',
          base_url: 'https://gw.example',
          api_key: REDACTED_SECRET_PLACEHOLDER,
          model: 'opus',
          note: '',
        },
      ],
    },
  };
}

/** The marker a config response carries in place of a stored key. */
const REDACTED_SECRET_PLACEHOLDER = '__ASTRBOT_REDACTED__';

const CLI_STATE = {
  clis: [
    {
      cli: 'claude_code',
      path: 'C:/Users/x/.claude/settings.json',
      exists: true,
      managed: false,
      backed_up: false,
      base_url: '',
      model: '',
      has_credential: false,
    },
  ],
};

function mountPage() {
  return mountWithVuetify(ThirdPartyAgentsPage, {
    global: {
      provide: {
        $confirm: vi.fn(async () => true),
      },
      stubs: {
        // Vuetify only mounts a dialog's content once it is open, so the stub
        // renders it straight away and the form can be driven without waiting.
        VDialog: {
          props: ['modelValue'],
          template: '<div v-if="modelValue"><slot /></div>',
        },
      },
    },
  });
}

type Wrapper = ReturnType<typeof mountPage>;

/** Add a provider through the provider editor and close its form. */
async function addProvider(wrapper: Wrapper, id: string, baseUrl: string) {
  await wrapper.findAll('.coding-cli-providers__add')[0].trigger('click');
  await wrapper.vm.$nextTick();
  await wrapper.find('.coding-cli-providers__form-id input').setValue(id);
  await wrapper
    .find('.coding-cli-providers__form-base-url input')
    .setValue(baseUrl);
  await wrapper.find('.coding-cli-providers__form-confirm').trigger('click');
  await wrapper.vm.$nextTick();
}

/** The config as it was sent to the profile endpoint. */
function savedConfig() {
  return testState.updateProfileMock.mock.calls[0][1] as {
    btw: { cli_providers: Record<string, unknown>[] };
  };
}

describe('ThirdPartyAgentsPage', () => {
  beforeEach(() => {
    testState.getProfileMock.mockResolvedValue({
      data: { status: 'ok', data: { config: configFixture() } },
    });
    testState.updateProfileMock.mockResolvedValue({
      data: { status: 'ok', message: 'saved' },
    });
    testState.cliStateMock.mockResolvedValue({
      data: { status: 'ok', data: CLI_STATE },
    });
    testState.switchMock.mockResolvedValue({
      data: { status: 'ok', data: CLI_STATE.clis[0] },
    });
    testState.removeMock.mockResolvedValue({
      data: { status: 'ok', data: CLI_STATE.clis[0] },
    });
  });

  it('shows the stored provider list of the running profile', async () => {
    const wrapper = mountPage();
    await flushPromises();

    // The running profile, because that is the list a switch resolves against.
    expect(testState.getProfileMock).toHaveBeenCalledWith('default');
    expect(testState.cliStateMock).toHaveBeenCalled();
    expect(wrapper.find('.coding-cli-providers__provider').exists()).toBe(true);
    // The agent editor lives on the BTW page, not here.
    expect(wrapper.find('.coding-agents-editor').exists()).toBe(false);
    wrapper.unmount();
  });

  it('saves the list the editor produced', async () => {
    const wrapper = mountPage();
    await flushPromises();

    await addProvider(wrapper, 'mine', 'https://mine.example');
    await wrapper.find('.third-party-agents-page__save').trigger('click');
    await flushPromises();

    expect(testState.updateProfileMock).toHaveBeenCalledWith(
      'default',
      expect.anything(),
      expect.objectContaining({ headers: {} }),
    );
    const ids = savedConfig().btw.cli_providers.map((entry) => entry.id);
    expect(ids).toEqual(['gw', 'mine']);
    // The marker goes back for the entry it came from, which is what the
    // profile resolves to the stored key, and nowhere else.
    expect(savedConfig().btw.cli_providers[0].api_key).toBe(
      REDACTED_SECRET_PLACEHOLDER,
    );
    // The provider that was just added has an id the profile has never seen,
    // so there is no stored key for it: posting the marker would store it.
    expect(savedConfig().btw.cli_providers[1].api_key).toBeUndefined();
    wrapper.unmount();
  });

  it('asks for the second factor when the save is challenged', async () => {
    testState.updateProfileMock.mockResolvedValue({
      status: 401,
      data: { status: 'error', data: { totp_required: true } },
    });

    const wrapper = mountPage();
    await flushPromises();

    await addProvider(wrapper, 'mine', 'https://mine.example');
    await wrapper.find('.third-party-agents-page__save').trigger('click');
    await flushPromises();

    expect(
      wrapper.findComponent(DashboardTwoFactorDialog).props('modelValue'),
    ).toBe(true);
    wrapper.unmount();
  });

  it('reports a load failure instead of rendering an empty page', async () => {
    testState.getProfileMock.mockRejectedValue(new Error('nope'));

    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain(
      'Could not read the provider list from the configuration profile',
    );
    wrapper.unmount();
  });
});

import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import DashboardTwoFactorDialog from '@/components/shared/DashboardTwoFactorDialog.vue';
import ThirdPartyAgentsPage from '@/views/ThirdPartyAgentsPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  getProfileMock: vi.fn(),
  updateProfileMock: vi.fn(),
  cliStateMock: vi.fn(),
  switchMock: vi.fn(),
  removeMock: vi.fn(),
  stepUpMock: vi.fn(),
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
    stepUp: testState.stepUpMock,
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
    {
      cli: 'codex',
      path: 'C:/Users/x/.codex/config.toml',
      exists: false,
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
        VSnackbar: {
          props: ['modelValue'],
          template: '<div v-if="modelValue"><slot /></div>',
        },
      },
    },
  });
}

type Wrapper = ReturnType<typeof mountPage>;

/** Add a provider through the provider editor and close its form. */
async function addProvider(
  wrapper: Wrapper,
  id: string,
  baseUrl: string,
  cliIndex = 0,
) {
  await wrapper
    .findAll('.coding-cli-providers__add')
    [cliIndex].trigger('click');
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

  it.each(['claude_code', 'codex'])(
    'saves a new %s provider before switching by id',
    async (cli) => {
      const wrapper = mountPage();
      await flushPromises();
      const cliIndex = CLI_STATE.clis.findIndex((state) => state.cli === cli);
      await addProvider(wrapper, 'mine', 'https://mine.example', cliIndex);
      const button = wrapper
        .findAll('.coding-cli-providers__cli')
        [cliIndex].findAll('.coding-cli-providers__switch')[1];

      await button.trigger('click');
      await flushPromises();

      expect(savedConfig().btw.cli_providers[1]).toMatchObject({
        id: 'mine',
        cli,
        base_url: 'https://mine.example',
      });
      expect(testState.updateProfileMock).toHaveBeenCalledWith(
        'default',
        expect.anything(),
        expect.anything(),
      );
      expect(testState.switchMock).toHaveBeenCalledWith(
        { cli, provider_id: 'mine' },
        { headers: {} },
      );
      expect(
        testState.updateProfileMock.mock.invocationCallOrder[0],
      ).toBeLessThan(testState.switchMock.mock.invocationCallOrder[0]);
      expect(
        wrapper.find('.third-party-agents-page__save').attributes('disabled'),
      ).toBeDefined();
      wrapper.unmount();
    },
  );

  it('switches a saved provider without saving the profile again', async () => {
    const wrapper = mountPage();
    await flushPromises();
    await wrapper.find('.coding-cli-providers__switch').trigger('click');
    await flushPromises();

    expect(testState.updateProfileMock).not.toHaveBeenCalled();
    expect(testState.switchMock).toHaveBeenCalledWith(
      { cli: 'claude_code', provider_id: 'gw' },
      { headers: {} },
    );
    wrapper.unmount();
  });

  it('saves edits to an existing provider before switching', async () => {
    const wrapper = mountPage();
    await flushPromises();
    await wrapper.find('.coding-cli-providers__edit').trigger('click');
    await wrapper
      .find('.coding-cli-providers__form-base-url input')
      .setValue('https://updated.example');
    await wrapper.find('.coding-cli-providers__form-confirm').trigger('click');
    await wrapper.find('.coding-cli-providers__switch').trigger('click');
    await flushPromises();

    expect(savedConfig().btw.cli_providers[0]).toMatchObject({
      base_url: 'https://updated.example',
      api_key: REDACTED_SECRET_PLACEHOLDER,
    });
    expect(
      testState.updateProfileMock.mock.invocationCallOrder[0],
    ).toBeLessThan(testState.switchMock.mock.invocationCallOrder[0]);
    wrapper.unmount();
  });

  it.each(['response', 'network'])(
    'aborts switching on a save %s error',
    async (failure) => {
      if (failure === 'response') {
        testState.updateProfileMock.mockResolvedValue({
          data: { status: 'error' },
        });
      } else {
        testState.updateProfileMock.mockRejectedValue(new Error('offline'));
      }
      const wrapper = mountPage();
      await flushPromises();
      await addProvider(wrapper, 'mine', 'https://mine.example');
      await wrapper
        .findAll('.coding-cli-providers__switch')[1]
        .trigger('click');
      await flushPromises();

      expect(testState.switchMock).not.toHaveBeenCalled();
      expect(wrapper.text()).toContain(
        'Could not save the third-party agent configuration',
      );
      expect(
        wrapper.find('.third-party-agents-page__save').attributes('disabled'),
      ).toBeUndefined();
      wrapper.unmount();
    },
  );

  it('stops for TOTP and allows switching after the challenged save succeeds', async () => {
    testState.updateProfileMock.mockResolvedValueOnce({
      status: 401,
      data: { status: 'error', data: { totp_required: true } },
    });
    const wrapper = mountPage();
    await flushPromises();
    await addProvider(wrapper, 'mine', 'https://mine.example');
    const button = wrapper.findAll('.coding-cli-providers__switch')[1];
    await button.trigger('click');
    await flushPromises();

    expect(testState.switchMock).not.toHaveBeenCalled();
    const dialog = wrapper.findComponent(DashboardTwoFactorDialog);
    expect(dialog.props('modelValue')).toBe(true);
    dialog.vm.$emit('confirm', '123456');
    await flushPromises();
    expect(testState.updateProfileMock).toHaveBeenLastCalledWith(
      'default',
      expect.anything(),
      expect.objectContaining({ headers: { 'X-2FA-Code': '123456' } }),
    );
    expect(testState.switchMock).not.toHaveBeenCalled();

    await button.trigger('click');
    await flushPromises();
    expect(testState.updateProfileMock).toHaveBeenCalledTimes(2);
    expect(testState.switchMock).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it.each([true, false])(
    'waits for profile step-up before switching (confirmed: %s)',
    async (confirmed) => {
      testState.updateProfileMock.mockRejectedValueOnce({
        response: { data: { data: { requires_step_up: true } } },
      });
      testState.stepUpMock.mockResolvedValue({
        data: { status: 'ok', data: { token: 'profile-token' } },
      });
      const wrapper = mountPage();
      await flushPromises();
      await addProvider(wrapper, 'mine', 'https://mine.example');
      await wrapper
        .findAll('.coding-cli-providers__switch')[1]
        .trigger('click');
      await flushPromises();

      expect(testState.switchMock).not.toHaveBeenCalled();
      const dialog = wrapper
        .findAllComponents(DashboardStepUpDialog)
        .find((candidate) => candidate.props('modelValue'))!;
      expect(dialog).toBeDefined();
      if (confirmed) {
        dialog.vm.$emit('confirm', { password: 'pw' });
      } else {
        dialog.vm.$emit('cancel');
      }
      await flushPromises();

      expect(testState.switchMock).toHaveBeenCalledTimes(confirmed ? 1 : 0);
      expect(testState.updateProfileMock).toHaveBeenCalledTimes(
        confirmed ? 2 : 1,
      );
      if (confirmed) {
        expect(testState.updateProfileMock).toHaveBeenLastCalledWith(
          'default',
          expect.anything(),
          expect.objectContaining({
            headers: { 'X-AstrBot-Step-Up': 'profile-token' },
          }),
        );
        expect(testState.switchMock).toHaveBeenCalledWith(
          { cli: 'claude_code', provider_id: 'mine' },
          { headers: {} },
        );
      }
      wrapper.unmount();
    },
  );

  it('keeps later edits unsaved and aborts switching while a save is pending', async () => {
    let finishSave!: (response: unknown) => void;
    testState.updateProfileMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishSave = resolve;
        }),
    );
    const wrapper = mountPage();
    await flushPromises();
    await addProvider(wrapper, 'mine', 'https://mine.example');
    await wrapper.findAll('.coding-cli-providers__switch')[1].trigger('click');
    await flushPromises();
    expect(testState.switchMock).not.toHaveBeenCalled();

    await addProvider(wrapper, 'later', 'https://later.example');
    await wrapper.findAll('.coding-cli-providers__switch')[2].trigger('click');
    await flushPromises();
    expect(testState.updateProfileMock).toHaveBeenCalledTimes(1);
    expect(testState.switchMock).not.toHaveBeenCalled();

    finishSave({ data: { status: 'ok' } });
    await flushPromises();
    expect(savedConfig().btw.cli_providers.map((entry) => entry.id)).toEqual([
      'gw',
      'mine',
    ]);
    expect(testState.switchMock).not.toHaveBeenCalled();
    expect(
      wrapper.find('.third-party-agents-page__save').attributes('disabled'),
    ).toBeUndefined();
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

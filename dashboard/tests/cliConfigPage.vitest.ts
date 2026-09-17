import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CliConfigPage from '@/views/CliConfigPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  stateMock: vi.fn(),
  switchMock: vi.fn(),
  removeMock: vi.fn(),
  getProfileMock: vi.fn(),
  updateProfileMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  codingCliApi: {
    state: testState.stateMock,
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
  authorizationApi: { stepUp: vi.fn(), webChatStepUp: vi.fn() },
}));

const STATE = {
  clis: [
    {
      cli: 'claude_code',
      path: 'C:/Users/x/.claude/settings.json',
      exists: true,
      managed: true,
      backed_up: true,
      // What the CLI's own file currently holds, which is what "in use" means.
      base_url: 'https://gw.example',
      model: 'opus',
      has_credential: true,
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

/** The operator's own list, which is what the cards render from. */
const CONFIG = {
  btw: {
    cli_providers: [
      {
        id: 'gw',
        name: 'Gateway',
        base_url: 'https://gw.example',
        api_key: 'sk-secret',
        model: 'opus',
        note: 'primary',
      },
      {
        id: 'local',
        name: 'Local',
        base_url: 'http://127.0.0.1:8080',
        model: '',
        note: '',
      },
    ],
  },
};

function mountPage(confirm = true) {
  return mountWithVuetify(CliConfigPage, {
    global: {
      provide: {
        // The app supplies this through a plugin; a mount supplies it here so
        // the confirmation never falls through to `window.confirm`.
        $confirm: vi.fn(async () => confirm),
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

/** The provider list as it was sent to the config profile endpoint. */
function savedProviders() {
  const body = testState.updateProfileMock.mock.calls[0][1] as {
    btw: { cli_providers: Record<string, unknown>[] };
  };
  return body.btw.cli_providers;
}

/** The card for one provider inside one CLI's section. */
function cardFor(
  wrapper: ReturnType<typeof mountPage>,
  cli: string,
  providerId: string,
) {
  const sections = wrapper.findAll('.cli-config-page__cli');
  const section = sections.find((node) =>
    node.text().includes(cli === 'codex' ? 'Codex' : 'Claude Code'),
  );
  if (!section) throw new Error(`no section for ${cli}`);
  const card = section
    .findAll('.cli-config-page__provider')
    .find((node) => node.text().includes(providerId));
  if (!card) throw new Error(`no card for ${providerId} in ${cli}`);
  return card;
}

async function openFormAndFill(
  wrapper: ReturnType<typeof mountPage>,
  values: { id: string; base_url?: string; api_key?: string },
) {
  await wrapper.findAll('.cli-config-page__add')[0].trigger('click');
  await wrapper.vm.$nextTick();
  await wrapper.find('.cli-config-page__form-id input').setValue(values.id);
  if (values.base_url !== undefined) {
    await wrapper
      .find('.cli-config-page__form-base-url input')
      .setValue(values.base_url);
  }
  if (values.api_key !== undefined) {
    await wrapper
      .find('.cli-config-page__form-api-key input')
      .setValue(values.api_key);
  }
  await wrapper.find('.cli-config-page__form-confirm').trigger('click');
  await wrapper.vm.$nextTick();
}

describe('CliConfigPage', () => {
  beforeEach(() => {
    testState.stateMock.mockResolvedValue({
      data: { status: 'ok', data: STATE },
    });
    testState.switchMock.mockResolvedValue({
      data: { status: 'ok', data: STATE.clis[0] },
    });
    testState.removeMock.mockResolvedValue({
      data: { status: 'ok', data: STATE.clis[0] },
    });
    testState.getProfileMock.mockResolvedValue({
      data: { status: 'ok', data: { config: CONFIG, metadata: {} } },
    });
    testState.updateProfileMock.mockResolvedValue({
      data: { status: 'ok', message: 'saved' },
    });
  });

  it('lists both CLIs with their own config path', async () => {
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain('Claude Code');
    expect(wrapper.text()).toContain('Codex');
    expect(wrapper.text()).toContain('C:/Users/x/.claude/settings.json');
    expect(wrapper.text()).toContain('C:/Users/x/.codex/config.toml');
    wrapper.unmount();
  });

  it('shows each provider card with its endpoint and state', async () => {
    const wrapper = mountPage();
    await flushPromises();

    const cards = wrapper
      .findAll('.cli-config-page__cli')[0]
      .findAll('.cli-config-page__provider');
    expect(cards).toHaveLength(2);
    expect(cards[0].text()).toContain('Gateway');
    expect(cards[0].text()).toContain('https://gw.example');
    expect(cards[0].find('.cli-config-page__current').exists()).toBe(true);
    // The second card is not the one in use, so it has no marker.
    expect(cards[1].find('.cli-config-page__current').exists()).toBe(false);
    wrapper.unmount();
  });

  it('switches the CLI to the provider whose card was clicked', async () => {
    const wrapper = mountPage();
    await flushPromises();

    const sections = wrapper.findAll('.cli-config-page__cli');
    const claude = sections[0];
    const cards = claude.findAll('.cli-config-page__provider');
    // The second card in the Claude section is the one not in use.
    await cards[1].find('.cli-config-page__switch').trigger('click');
    await flushPromises();

    expect(testState.switchMock).toHaveBeenCalledWith(
      { cli: 'claude_code', provider_id: 'local' },
      { headers: {} },
    );
    wrapper.unmount();
  });

  it('does not offer a switch for the provider already in use', async () => {
    const wrapper = mountPage();
    await flushPromises();

    const buttons = wrapper
      .findAll('.cli-config-page__cli')[0]
      .findAll('.cli-config-page__switch');
    expect(buttons[0].classes().some((name) => name.includes('disabled'))).toBe(
      true,
    );
    expect(buttons[1].classes().some((name) => name.includes('disabled'))).toBe(
      false,
    );
    wrapper.unmount();
  });

  it('adds a provider through the form and saves the list', async () => {
    const wrapper = mountPage();
    await flushPromises();

    await openFormAndFill(wrapper, {
      id: 'mine',
      base_url: 'https://mine.example',
      api_key: 'sk-2',
    });
    await wrapper.find('.cli-config-page__save').trigger('click');
    await flushPromises();

    const added = savedProviders().find((entry) => entry.id === 'mine');
    expect(added?.base_url).toBe('https://mine.example');
    expect(added?.api_key).toBe('sk-2');
    wrapper.unmount();
  });

  it('leaves a stored key alone when the field is left empty', async () => {
    const wrapper = mountPage();
    await flushPromises();

    await cardFor(wrapper, 'claude_code', 'gw')
      .find('.cli-config-page__edit')
      .trigger('click');
    await wrapper.vm.$nextTick();
    const keyInput = wrapper.find('.cli-config-page__form-api-key input')
      .element as HTMLInputElement;
    // The API never sends a key back, so the field starts empty, and empty has
    // to mean "unchanged" rather than "erase it".
    expect(keyInput.value).toBe('');

    // Something has to change for there to be anything to save.
    await wrapper
      .find('.cli-config-page__form-note input')
      .setValue('updated note');
    await wrapper.find('.cli-config-page__form-confirm').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('.cli-config-page__save').trigger('click');
    await flushPromises();

    const entry = savedProviders().find((item) => item.id === 'gw');
    expect(entry?.api_key).toBe('sk-secret');
    expect(entry?.note).toBe('updated note');
    wrapper.unmount();
  });

  it('refuses a provider with no endpoint and no key', async () => {
    const wrapper = mountPage();
    await flushPromises();

    await openFormAndFill(wrapper, { id: 'bare' });

    expect(wrapper.find('.cli-config-page__form-error').exists()).toBe(true);
    await wrapper.find('.cli-config-page__save').trigger('click');
    await flushPromises();
    expect(testState.updateProfileMock).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('mounts without Vue warnings when a class is injected from above', async () => {
    // The page is mounted through an injected slot, which passes a class down.
    // A fragment root would warn about extraneous attributes instead of
    // rendering, and that warning is what the smoke suites fail on.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});

    const wrapper = mountWithVuetify(CliConfigPage, {
      attrs: { class: 'cli-config-page-test' },
      attachTo: document.body,
    });
    await flushPromises();

    expect(wrapper.classes()).toContain('cli-config-page-test');
    const noisy = [...warn.mock.calls, ...error.mock.calls].filter((args) =>
      args.some((arg) =>
        String(arg).includes('Extraneous non-props attributes'),
      ),
    );
    expect(noisy).toHaveLength(0);

    warn.mockRestore();
    error.mockRestore();
    wrapper.unmount();
  });

  it('reports a load failure instead of an empty page', async () => {
    testState.stateMock.mockRejectedValue(new Error('nope'));

    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain('Could not read the CLI configuration');
    wrapper.unmount();
  });

  it('restores from the backup', async () => {
    const wrapper = mountPage();
    await flushPromises();

    await wrapper.find('.cli-config-page__restore').trigger('click');
    await flushPromises();

    expect(testState.removeMock).toHaveBeenCalledWith('claude_code', {
      headers: {},
    });
    wrapper.unmount();
  });
});

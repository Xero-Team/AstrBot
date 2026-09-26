import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CodingCliProviders from '@/components/shared/CodingCliProviders.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import type { StoredCliProvider } from '@/api/v1';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  stateMock: vi.fn(),
  switchMock: vi.fn(),
  removeMock: vi.fn(),
  stepUpMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  codingCliApi: {
    state: testState.stateMock,
    switchProvider: testState.switchMock,
    remove: testState.removeMock,
  },
}));

vi.mock('@/api/v1/authorization', () => ({
  STEP_UP_TTL_SECONDS: 300,
  authorizationApi: {
    stepUp: testState.stepUpMock,
    webChatStepUp: vi.fn(),
  },
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

/**
 * The operator's own list, as the page hands it over.
 *
 * `api_key` is empty and `has_api_key` is true for the entry whose key the
 * profile holds: the page reads the marker a response carries as "a key is
 * stored, the field is empty" and puts the marker back only for this entry.
 */
const PROVIDERS: StoredCliProvider[] = [
  {
    id: 'gw',
    name: 'Gateway',
    base_url: 'https://gw.example',
    api_key: '',
    model: 'opus',
    note: 'primary',
    has_api_key: true,
    current: false,
    cli: '',
  },
  {
    id: 'local',
    name: 'Local',
    base_url: 'http://127.0.0.1:8080',
    api_key: '',
    model: '',
    note: '',
    has_api_key: false,
    current: false,
    cli: '',
  },
];

function mountProviders(
  providers: StoredCliProvider[] = PROVIDERS,
  confirm = true,
  beforeSwitch = vi.fn(async () => true),
) {
  return mountWithVuetify(CodingCliProviders, {
    props: { modelValue: providers, beforeSwitch },
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

type Wrapper = ReturnType<typeof mountProviders>;

/** The provider list as it was last emitted for the page to save. */
function emittedProviders(wrapper: Wrapper): StoredCliProvider[] {
  const emitted = wrapper.emitted('update:modelValue');
  expect(emitted).toBeTruthy();
  return emitted!.at(-1)![0] as StoredCliProvider[];
}

/** The card for one provider inside one CLI's section. */
function cardFor(wrapper: Wrapper, cli: string, providerId: string) {
  const sections = wrapper.findAll('.coding-cli-providers__cli');
  const section = sections.find((node) =>
    node.text().includes(cli === 'codex' ? 'Codex' : 'Claude Code'),
  );
  if (!section) throw new Error(`no section for ${cli}`);
  const card = section
    .findAll('.coding-cli-providers__provider')
    .find((node) => node.text().includes(providerId));
  if (!card) throw new Error(`no card for ${providerId} in ${cli}`);
  return card;
}

async function openFormAndFill(
  wrapper: Wrapper,
  values: { id: string; base_url?: string; api_key?: string },
) {
  await wrapper.findAll('.coding-cli-providers__add')[0].trigger('click');
  await wrapper.vm.$nextTick();
  await wrapper
    .find('.coding-cli-providers__form-id input')
    .setValue(values.id);
  if (values.base_url !== undefined) {
    await wrapper
      .find('.coding-cli-providers__form-base-url input')
      .setValue(values.base_url);
  }
  if (values.api_key !== undefined) {
    await wrapper
      .find('.coding-cli-providers__form-api-key input')
      .setValue(values.api_key);
  }
  await wrapper.find('.coding-cli-providers__form-confirm').trigger('click');
  await wrapper.vm.$nextTick();
}

describe('CodingCliProviders', () => {
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
  });

  it('lists both CLIs with their own config path', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    expect(wrapper.text()).toContain('Claude Code');
    expect(wrapper.text()).toContain('Codex');
    expect(wrapper.text()).toContain('C:/Users/x/.claude/settings.json');
    expect(wrapper.text()).toContain('C:/Users/x/.codex/config.toml');
    wrapper.unmount();
  });

  it('shows each provider card with its endpoint and state', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    const cards = wrapper
      .findAll('.coding-cli-providers__cli')[0]
      .findAll('.coding-cli-providers__provider');
    expect(cards).toHaveLength(2);
    expect(cards[0].text()).toContain('Gateway');
    expect(cards[0].text()).toContain('https://gw.example');
    expect(cards[0].find('.coding-cli-providers__current').exists()).toBe(true);
    // The second card is not the one in use, so it has no marker.
    expect(cards[1].find('.coding-cli-providers__current').exists()).toBe(
      false,
    );
    wrapper.unmount();
  });

  it('switches the CLI to the provider whose card was clicked', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    const claude = wrapper.findAll('.coding-cli-providers__cli')[0];
    const cards = claude.findAll('.coding-cli-providers__provider');
    // The second card in the Claude section is the one not in use.
    await cards[1].find('.coding-cli-providers__switch').trigger('click');
    await flushPromises();

    expect(testState.switchMock).toHaveBeenCalledWith(
      { cli: 'claude_code', provider_id: 'local' },
      { headers: {} },
    );
    wrapper.unmount();
  });

  it('does not offer a switch for the provider already in use', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    const buttons = wrapper
      .findAll('.coding-cli-providers__cli')[0]
      .findAll('.coding-cli-providers__switch');
    expect(buttons[0].classes().some((name) => name.includes('disabled'))).toBe(
      true,
    );
    expect(buttons[1].classes().some((name) => name.includes('disabled'))).toBe(
      false,
    );
    wrapper.unmount();
  });

  it('does not save or switch when confirmation is cancelled', async () => {
    const beforeSwitch = vi.fn(async () => true);
    const wrapper = mountProviders(PROVIDERS, false, beforeSwitch);
    await flushPromises();
    await cardFor(wrapper, 'claude_code', 'Local')
      .find('.coding-cli-providers__switch')
      .trigger('click');
    await flushPromises();

    expect(beforeSwitch).not.toHaveBeenCalled();
    expect(testState.switchMock).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('waits for the profile save before requesting a switch', async () => {
    let finishSave!: (saved: boolean) => void;
    const beforeSwitch = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          finishSave = resolve;
        }),
    );
    const wrapper = mountProviders(PROVIDERS, true, beforeSwitch);
    await flushPromises();
    await cardFor(wrapper, 'claude_code', 'Local')
      .find('.coding-cli-providers__switch')
      .trigger('click');
    await flushPromises();

    expect(beforeSwitch).toHaveBeenCalledTimes(1);
    expect(testState.switchMock).not.toHaveBeenCalled();
    finishSave(true);
    await flushPromises();
    expect(testState.switchMock).toHaveBeenCalledWith(
      { cli: 'claude_code', provider_id: 'local' },
      { headers: {} },
    );
    wrapper.unmount();
  });

  it('still requests the CLI write step-up after saving', async () => {
    testState.switchMock.mockRejectedValueOnce({
      response: { data: { data: { requires_step_up: true } } },
    });
    testState.stepUpMock.mockResolvedValue({
      data: { status: 'ok', data: { token: 'cli-token' } },
    });
    const beforeSwitch = vi.fn(async () => true);
    const wrapper = mountProviders(PROVIDERS, true, beforeSwitch);
    await flushPromises();
    await cardFor(wrapper, 'claude_code', 'Local')
      .find('.coding-cli-providers__switch')
      .trigger('click');
    await flushPromises();

    const dialog = wrapper.findComponent(DashboardStepUpDialog);
    expect(dialog.props('modelValue')).toBe(true);
    dialog.vm.$emit('confirm', { password: 'pw' });
    await flushPromises();

    expect(beforeSwitch).toHaveBeenCalledTimes(1);
    expect(testState.stepUpMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'coding_cli.config.write',
        resource_type: 'instance',
        resource_id: 'default',
      }),
    );
    expect(testState.switchMock).toHaveBeenLastCalledWith(
      { cli: 'claude_code', provider_id: 'local' },
      { headers: { 'X-AstrBot-Step-Up': 'cli-token' } },
    );
    wrapper.unmount();
  });

  it('edits the list the page saves, leaving the stored key alone', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    await cardFor(wrapper, 'claude_code', 'gw')
      .find('.coding-cli-providers__edit')
      .trigger('click');
    await wrapper.vm.$nextTick();
    const keyInput = wrapper.find('.coding-cli-providers__form-api-key input')
      .element as HTMLInputElement;
    // The form never shows the stored key, so the field starts empty, and
    // empty has to mean "unchanged" rather than "erase it".
    expect(keyInput.value).toBe('');

    await wrapper
      .find('.coding-cli-providers__form-note input')
      .setValue('updated note');
    await wrapper.find('.coding-cli-providers__form-confirm').trigger('click');
    await wrapper.vm.$nextTick();

    const entry = emittedProviders(wrapper).find((item) => item.id === 'gw');
    // The key is reported as still stored and its value is not in the list at
    // all; the page is what turns that back into the marker the profile
    // resolves, and only for the entry whose id the marker came from.
    expect(entry?.api_key).toBe('');
    expect(entry?.has_api_key).toBe(true);
    expect(entry?.note).toBe('updated note');
    wrapper.unmount();
  });

  it('adds a provider scoped to the CLI whose section it was added from', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    // `openFormAndFill` adds from the Claude Code section, the first one.
    await openFormAndFill(wrapper, {
      id: 'mine',
      base_url: 'https://mine.example',
      api_key: 'sk-2',
    });

    // Scoped, not left open: an entry with no `cli` is shown under every CLI,
    // so leaving it unset would put a Claude provider in the Codex section too.
    const added = emittedProviders(wrapper).find(
      (entry) => entry.id === 'mine',
    );
    expect(added?.cli).toBe('claude_code');
    wrapper.unmount();
  });

  it('does not carry a stored key onto a duplicate', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    await cardFor(wrapper, 'claude_code', 'gw')
      .find('.coding-cli-providers__duplicate')
      .trigger('click');
    await wrapper.vm.$nextTick();

    const copy = emittedProviders(wrapper).find(
      (entry) => entry.id === 'gw-copy',
    );
    // Metadata only.  Copying `has_api_key` would make the page post the
    // source's marker under a new id, which the profile cannot resolve -- and
    // a switch would then write the marker into the CLI's own file as a key.
    expect(copy?.has_api_key).toBe(false);
    expect(copy?.api_key).toBe('');
    expect(copy?.base_url).toBe('https://gw.example');
    wrapper.unmount();
  });

  it('refuses an id another provider already uses, whichever CLI it is under', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    // `gw` is unscoped and so is listed under both CLIs, but the profile keys
    // its list by id alone: a second `gw` would be dropped on the next load.
    await openFormAndFill(wrapper, {
      id: 'gw',
      base_url: 'https://other.example',
    });

    expect(wrapper.find('.coding-cli-providers__form-error').exists()).toBe(
      true,
    );
    wrapper.unmount();
  });

  it('adds a provider through the form', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    await openFormAndFill(wrapper, {
      id: 'mine',
      base_url: 'https://mine.example',
      api_key: 'sk-2',
    });

    const added = emittedProviders(wrapper).find(
      (entry) => entry.id === 'mine',
    );
    expect(added?.base_url).toBe('https://mine.example');
    expect(added?.api_key).toBe('sk-2');
    wrapper.unmount();
  });

  it('refuses a provider with no endpoint and no key', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    await openFormAndFill(wrapper, { id: 'bare' });

    expect(wrapper.find('.coding-cli-providers__form-error').exists()).toBe(
      true,
    );
    expect(wrapper.emitted('update:modelValue')).toBeFalsy();
    wrapper.unmount();
  });

  it('answers a step-up challenge instead of dead-ending on the load', async () => {
    // A read is an ordinary permission, but a session that has not proved
    // itself is answered with a challenge.  Without answering it the page has
    // nothing to retry with, so it would never fill in.
    testState.stateMock
      .mockRejectedValueOnce({
        response: { data: { data: { requires_step_up: true } } },
      })
      .mockResolvedValueOnce({ data: { status: 'ok', data: STATE } });
    testState.stepUpMock.mockResolvedValue({
      data: { status: 'ok', data: { token: 'token-1' } },
    });

    const wrapper = mountProviders();
    await flushPromises();

    const dialog = wrapper.findComponent(DashboardStepUpDialog);
    expect(dialog.props('modelValue')).toBe(true);
    dialog.vm.$emit('confirm', { password: 'pw', code: '123456' });
    await flushPromises();

    expect(testState.stepUpMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'platform.read',
        resource_type: 'instance',
        resource_id: 'default',
      }),
    );
    expect(testState.stateMock).toHaveBeenLastCalledWith({
      headers: { 'X-AstrBot-Step-Up': 'token-1' },
    });
    expect(wrapper.text()).toContain('Claude Code');
    wrapper.unmount();
  });

  it('reports a load failure instead of an empty list', async () => {
    testState.stateMock.mockRejectedValue(new Error('nope'));

    const wrapper = mountProviders();
    await flushPromises();

    expect(wrapper.text()).toContain('Could not read the CLI configuration');
    wrapper.unmount();
  });

  it('restores from the backup', async () => {
    const wrapper = mountProviders();
    await flushPromises();

    await wrapper.find('.coding-cli-providers__restore').trigger('click');
    await flushPromises();

    expect(testState.removeMock).toHaveBeenCalledWith('claude_code', {
      headers: {},
    });
    wrapper.unmount();
  });

  it('mounts without Vue warnings when a class is injected from above', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});

    const wrapper = mountWithVuetify(CodingCliProviders, {
      attrs: { class: 'coding-cli-providers-test' },
      props: { modelValue: PROVIDERS, beforeSwitch: async () => true },
    });
    await flushPromises();

    expect(wrapper.classes()).toContain('coding-cli-providers-test');
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
});

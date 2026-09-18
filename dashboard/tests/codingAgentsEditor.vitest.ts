import { afterEach, describe, expect, it, vi } from 'vitest';
import CodingAgentsEditor from '@/components/shared/CodingAgentsEditor.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

/** The projected shape the editor emits, for one agent with no presets. */
const claudeAgent = {
  id: 'claude_code',
  name: 'Claude Code',
  type: 'claude_code',
  enabled: true,
  command: 'claude',
  model: '',
  permission_mode: 'acceptEdits',
  sandbox: 'workspace-write',
  project_dir: '',
  extra_args: [],
  env: {},
  timeout_seconds: 1800,
  max_output_chars: 20000,
  active_provider: 'official',
  providers: [
    {
      id: 'official',
      name: 'official',
      base_url: '',
      api_key: '',
      model: '',
      wire_api: 'responses',
    },
  ],
};

function mountEditor(modelValue: unknown) {
  return mountWithVuetify(CodingAgentsEditor, {
    props: { modelValue },
  });
}

/** The component behind one classed control, so its value can be driven. */
function control(wrapper: ReturnType<typeof mountEditor>, selector: string) {
  const found = wrapper.findComponent(selector);
  expect(found.exists(), `${selector} should be rendered`).toBe(true);
  return found;
}

function lastEmitted(wrapper: ReturnType<typeof mountEditor>) {
  const emitted = wrapper.emitted('update:modelValue');
  expect(emitted).toBeTruthy();
  const value = emitted!.at(-1)![0] as Record<string, unknown>[];
  return value;
}

describe('CodingAgentsEditor', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('allows class attrs without fragment warnings', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const wrapper = mountWithVuetify(CodingAgentsEditor, {
      attrs: { class: 'config-field' },
      props: { modelValue: [claudeAgent] },
    });

    expect(wrapper.classes()).toContain('config-field');
    expect(
      warnSpy.mock.calls.some((args) =>
        String(args[0]).includes('Extraneous non-props attributes'),
      ),
    ).toBe(false);
    wrapper.unmount();
  });

  it.each([[null], ['oops'], [undefined], [[null, 7]]])(
    'renders the empty state for the malformed value %s',
    (modelValue) => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      const wrapper = mountEditor(modelValue);

      expect(wrapper.find('.coding-agents-editor__empty').exists()).toBe(true);
      expect(wrapper.find('.coding-agents-editor__agent').exists()).toBe(false);
      expect(errorSpy).not.toHaveBeenCalled();
      expect(
        warnSpy.mock.calls.some((args) =>
          String(args[0]).includes('Extraneous non-props attributes'),
        ),
      ).toBe(false);
      wrapper.unmount();
    },
  );

  it('shows the fields each agent type actually uses', () => {
    const wrapper = mountEditor([
      { ...claudeAgent },
      { ...claudeAgent, id: 'codex', type: 'codex' },
      { ...claudeAgent, id: 'other', type: 'custom', command: 'other-cli' },
    ]);

    const agents = wrapper.findAll('.coding-agents-editor__agent');
    expect(agents).toHaveLength(3);

    expect(
      agents[0].find('.coding-agents-editor__permission-mode').exists(),
    ).toBe(true);
    expect(agents[0].find('.coding-agents-editor__sandbox').exists()).toBe(
      false,
    );
    expect(
      agents[1].find('.coding-agents-editor__permission-mode').exists(),
    ).toBe(false);
    expect(agents[1].find('.coding-agents-editor__sandbox').exists()).toBe(
      true,
    );
    expect(
      agents[2].find('.coding-agents-editor__permission-mode').exists(),
    ).toBe(false);
    expect(agents[2].find('.coding-agents-editor__sandbox').exists()).toBe(
      false,
    );

    // The wire API is a Codex field: only `_codex_profile` writes it.
    expect(
      agents[0].find('.coding-agents-editor__provider-wire-api').exists(),
    ).toBe(false);
    expect(
      agents[1].find('.coding-agents-editor__provider-wire-api').exists(),
    ).toBe(true);
    expect(
      agents[2].find('.coding-agents-editor__provider-wire-api').exists(),
    ).toBe(false);

    for (const agent of agents) {
      expect(agent.find('.coding-agents-editor__command').exists()).toBe(true);
      expect(agent.find('.coding-agents-editor__extra-args').exists()).toBe(
        true,
      );
      expect(agent.find('.coding-agents-editor__env').exists()).toBe(true);
      expect(agent.find('.coding-agents-editor__providers').exists()).toBe(
        true,
      );
    }
    wrapper.unmount();
  });

  it('emits the whole normalized list once, and only after an edit', async () => {
    const wrapper = mountEditor([claudeAgent]);
    expect(wrapper.emitted('update:modelValue')).toBeFalsy();

    control(wrapper, '.coding-agents-editor__name').vm.$emit(
      'update:modelValue',
      'My Claude',
    );
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted('update:modelValue')).toHaveLength(1);
    expect(lastEmitted(wrapper)).toEqual([
      { ...claudeAgent, name: 'My Claude' },
    ]);
    wrapper.unmount();
  });

  it('adds an agent with a unique id, a default command and disabled', async () => {
    const wrapper = mountEditor([claudeAgent]);

    await wrapper.find('.coding-agents-editor__add-agent').trigger('click');

    const emitted = lastEmitted(wrapper);
    expect(emitted).toHaveLength(2);
    expect(emitted[1]).toEqual({
      id: 'agent',
      name: '',
      type: 'claude_code',
      enabled: false,
      command: 'claude',
      model: '',
      permission_mode: 'acceptEdits',
      sandbox: 'workspace-write',
      project_dir: '',
      extra_args: [],
      env: {},
      timeout_seconds: 1800,
      max_output_chars: 20000,
      active_provider: '',
      providers: [],
    });
    wrapper.unmount();
  });

  it('does not reuse an id that is already taken', async () => {
    const wrapper = mountEditor([{ ...claudeAgent, id: 'agent' }]);

    await wrapper.find('.coding-agents-editor__add-agent').trigger('click');

    expect(lastEmitted(wrapper)[1]).toMatchObject({ id: 'agent-2' });
    wrapper.unmount();
  });

  it('removes and reorders agents, and bounds the move buttons', async () => {
    const second = { ...claudeAgent, id: 'second', name: 'Second' };
    const wrapper = mountEditor([claudeAgent, second]);

    const cards = wrapper.findAll('.coding-agents-editor__agent');
    expect(
      cards[0]
        .find('.coding-agents-editor__move-up')
        .classes()
        .some((name) => name.includes('disabled')),
    ).toBe(true);
    expect(
      cards[1]
        .find('.coding-agents-editor__move-down')
        .classes()
        .some((name) => name.includes('disabled')),
    ).toBe(true);

    await cards[0].find('.coding-agents-editor__move-down').trigger('click');
    const reordered = lastEmitted(wrapper);
    expect(reordered.map((entry) => entry.id)).toEqual([
      'second',
      'claude_code',
    ]);

    await wrapper.setProps({ modelValue: reordered });
    await wrapper
      .findAll('.coding-agents-editor__agent')[0]
      .find('.coding-agents-editor__remove-agent')
      .trigger('click');
    expect(lastEmitted(wrapper).map((entry) => entry.id)).toEqual([
      'claude_code',
    ]);
    wrapper.unmount();
  });

  it('activates a new preset only when none was active', async () => {
    const unset = { ...claudeAgent, active_provider: '', providers: [] };
    const wrapper = mountEditor([unset]);

    await wrapper.find('.coding-agents-editor__add-provider').trigger('click');

    const added = lastEmitted(wrapper)[0];
    expect(added.providers).toEqual([
      {
        id: 'provider',
        name: 'provider',
        base_url: '',
        api_key: '',
        model: '',
        wire_api: 'responses',
      },
    ]);
    expect(added.active_provider).toBe('provider');
    wrapper.unmount();

    const configured = mountEditor([{ ...claudeAgent }]);
    await configured
      .find('.coding-agents-editor__add-provider')
      .trigger('click');
    expect(lastEmitted(configured)[0].active_provider).toBe('official');
    configured.unmount();
  });

  it('repoints the active preset when the active one is removed', async () => {
    const wrapper = mountEditor([
      {
        ...claudeAgent,
        active_provider: 'official',
        providers: [...claudeAgent.providers, { id: 'gw', name: 'gw' }],
      },
    ]);

    await wrapper
      .find('.coding-agents-editor__remove-provider')
      .trigger('click');

    const entry = lastEmitted(wrapper)[0];
    expect((entry.providers as { id: string }[]).map((p) => p.id)).toEqual([
      'gw',
    ]);
    expect(entry.active_provider).toBe('gw');
    wrapper.unmount();
  });

  it('keeps a renamed preset active instead of falling back to the first', async () => {
    const wrapper = mountEditor([
      {
        ...claudeAgent,
        // Active, and not first: renaming it must not repoint to `official`.
        active_provider: 'gw',
        providers: [
          {
            id: 'gw',
            name: 'gw',
            base_url: '',
            api_key: '',
            model: '',
            wire_api: 'responses',
          },
          {
            id: 'official',
            name: 'official',
            base_url: '',
            api_key: '',
            model: '',
            wire_api: 'responses',
          },
        ],
      },
    ]);

    control(wrapper, '.coding-agents-editor__provider-id').vm.$emit(
      'update:modelValue',
      'gateway',
    );
    await wrapper.vm.$nextTick();

    const entry = lastEmitted(wrapper)[0];
    expect(entry.active_provider).toBe('gateway');
    wrapper.unmount();
  });

  it('round-trips extra arguments as a list', async () => {
    const wrapper = mountEditor([
      { ...claudeAgent, extra_args: ['--verbose'] },
    ]);

    const list = wrapper
      .find('.coding-agents-editor__extra-args')
      .findComponent({ name: 'ListConfigItem' });
    expect(list.exists()).toBe(true);
    list.vm.$emit('update:modelValue', ['--verbose', '--debug']);
    await wrapper.vm.$nextTick();

    expect(lastEmitted(wrapper)[0].extra_args).toEqual([
      '--verbose',
      '--debug',
    ]);
    wrapper.unmount();
  });

  it('round-trips environment variables as NAME=value lines', async () => {
    const wrapper = mountEditor([
      { ...claudeAgent, env: { ANTHROPIC_MODEL: 'opus' } },
    ]);

    const list = wrapper
      .find('.coding-agents-editor__env')
      .findComponent({ name: 'ListConfigItem' });
    expect(list.exists()).toBe(true);
    expect(list.props('modelValue')).toEqual(['ANTHROPIC_MODEL=opus']);

    list.vm.$emit('update:modelValue', [
      'A=1',
      'B=2=3',
      'no-equals',
      '=orphan',
    ]);
    await wrapper.vm.$nextTick();

    // A value keeps its own `=`; a line with no name names nothing.
    expect(lastEmitted(wrapper)[0].env).toEqual({
      A: '1',
      B: '2=3',
      'no-equals': '',
    });
    wrapper.unmount();
  });

  it('projects a malformed entry the way the backend would read it', async () => {
    const wrapper = mountEditor([
      {
        id: 42,
        type: 'nope',
        enabled: 'yes',
        permission_mode: 'bogus',
        sandbox: null,
        extra_args: 'oops',
        env: ['oops'],
        timeout_seconds: 'x',
        max_output_chars: 5,
        providers: [null, { id: '' }, { id: 'p' }],
      },
    ]);

    control(wrapper, '.coding-agents-editor__type').vm.$emit(
      'update:modelValue',
      'codex',
    );
    await wrapper.vm.$nextTick();

    expect(lastEmitted(wrapper)).toEqual([
      {
        id: '',
        name: '',
        type: 'codex',
        enabled: false,
        command: 'codex',
        model: '',
        permission_mode: 'acceptEdits',
        sandbox: 'workspace-write',
        project_dir: '',
        extra_args: [],
        env: {},
        timeout_seconds: 1800,
        max_output_chars: 20000,
        active_provider: 'p',
        providers: [
          {
            id: 'p',
            name: 'p',
            base_url: '',
            api_key: '',
            model: '',
            wire_api: 'responses',
          },
        ],
      },
    ]);
    wrapper.unmount();
  });

  it('marks an unusable entry without dropping it', async () => {
    const wrapper = mountEditor([
      { id: '', type: 'custom', command: '', enabled: false },
    ]);

    expect(wrapper.find('.coding-agents-editor__agent').exists()).toBe(true);
    const warnings = wrapper.find('.coding-agents-editor__warning').text();
    expect(warnings).toContain('ignored when the configuration is read');
    expect(warnings.length).toBeGreaterThan(0);
    expect(wrapper.emitted('update:modelValue')).toBeFalsy();
    wrapper.unmount();
  });

  it('warns about the permission choices that leave the boundary open', () => {
    const wrapper = mountEditor([
      { ...claudeAgent, permission_mode: 'bypassPermissions' },
      {
        ...claudeAgent,
        id: 'codex',
        type: 'codex',
        sandbox: 'danger-full-access',
      },
    ]);

    const cards = wrapper.findAll('.coding-agents-editor__agent');
    expect(cards[0].find('.coding-agents-editor__warning').text()).toContain(
      'bypassPermissions',
    );
    expect(cards[1].find('.coding-agents-editor__warning').text()).toContain(
      'danger-full-access',
    );
    wrapper.unmount();
  });

  it('follows the type default command without overwriting a typed one', async () => {
    const wrapper = mountEditor([{ ...claudeAgent }]);
    const type = control(wrapper, '.coding-agents-editor__type');

    type.vm.$emit('update:modelValue', 'codex');
    await wrapper.vm.$nextTick();
    expect(lastEmitted(wrapper)[0]).toMatchObject({
      type: 'codex',
      command: 'codex',
    });
    wrapper.unmount();

    const typed = mountEditor([{ ...claudeAgent, command: 'my-claude' }]);
    control(typed, '.coding-agents-editor__type').vm.$emit(
      'update:modelValue',
      'codex',
    );
    await typed.vm.$nextTick();
    expect(lastEmitted(typed)[0]).toMatchObject({
      type: 'codex',
      command: 'my-claude',
    });
    typed.unmount();
  });
});

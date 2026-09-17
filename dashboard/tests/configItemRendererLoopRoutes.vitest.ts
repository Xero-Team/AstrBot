import { describe, expect, it, vi } from 'vitest';
import ConfigItemRenderer from '@/components/shared/ConfigItemRenderer.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/utils/monacoLoader', () => ({}));

vi.mock('@guolao/vue-monaco-editor', () => ({
  VueMonacoEditor: {
    name: 'VueMonacoEditor',
    template: '<div class="monaco-editor-stub"></div>',
  },
}));

function mountRenderer(special: string) {
  return mountWithVuetify(ConfigItemRenderer, {
    props: {
      modelValue: [],
      itemMeta: { type: 'list', _special: special },
    },
    global: {
      stubs: {
        PluginLoopSelector: {
          template: '<div class="plugin-loop-stub"></div>',
        },
        CapabilityLoopSelector: {
          props: ['kind'],
          template: '<div class="capability-loop-stub">{{ kind }}</div>',
        },
        CodingAgentsEditor: {
          template: '<div class="coding-agents-stub"></div>',
        },
        ListConfigItem: {
          template: '<div class="list-config-stub"></div>',
        },
      },
    },
  });
}

describe('ConfigItemRenderer loop-route specials', () => {
  it('renders PluginLoopSelector for plugin loop assignments', () => {
    const wrapper = mountRenderer('select_plugin_loop_routes');
    expect(wrapper.find('.plugin-loop-stub').exists()).toBe(true);
    expect(wrapper.find('.list-config-stub').exists()).toBe(false);
    wrapper.unmount();
  });

  it('renders CapabilityLoopSelector for MCP and Skill loop assignments', () => {
    const mcp = mountRenderer('select_mcp_loop_routes');
    expect(mcp.find('.capability-loop-stub').text()).toBe('mcp');
    expect(mcp.find('.list-config-stub').exists()).toBe(false);
    mcp.unmount();

    const skill = mountRenderer('select_skill_loop_routes');
    expect(skill.find('.capability-loop-stub').text()).toBe('skill');
    expect(skill.find('.list-config-stub').exists()).toBe(false);
    skill.unmount();
  });

  it('renders CodingAgentsEditor for a coding-agent profile', () => {
    // The regression guard: a `_special` with no branch falls through to the
    // string-list editor, which cannot hold the objects this value is made of.
    const wrapper = mountRenderer('select_coding_agents');
    expect(wrapper.find('.coding-agents-stub').exists()).toBe(true);
    expect(wrapper.find('.list-config-stub').exists()).toBe(false);
    wrapper.unmount();
  });
});

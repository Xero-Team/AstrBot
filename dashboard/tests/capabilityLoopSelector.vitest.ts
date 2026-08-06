import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CapabilityLoopSelector from '@/components/shared/CapabilityLoopSelector.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  mcpListMock: vi.fn(),
  skillListMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  mcpApi: {
    list: testState.mcpListMock,
  },
  skillApi: {
    list: testState.skillListMock,
  },
}));

describe('CapabilityLoopSelector', () => {
  beforeEach(() => {
    testState.mcpListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          { name: 'workspace-mcp', active: true },
          { name: 'disabled-mcp', active: false },
        ],
      },
    });
    testState.skillListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          skills: [
            { name: 'workspace-skill', active: true },
            { name: 'disabled-skill', active: false },
          ],
        },
      },
    });
  });

  it('writes only a non-default MCP server assignment', async () => {
    const wrapper = mountWithVuetify(CapabilityLoopSelector, {
      props: {
        kind: 'mcp',
        modelValue: [],
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain('workspace-mcp');
    expect(wrapper.text()).not.toContain('disabled-mcp');

    const select = wrapper.findComponent({ name: 'VSelect' });
    select.vm.$emit('update:modelValue', 'work');
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted('update:modelValue')).toEqual([
      [[{ server_name: 'workspace-mcp', loop: 'work' }]],
    ]);
    wrapper.unmount();
  });

  it('uses Skill names as the assignment key', async () => {
    const wrapper = mountWithVuetify(CapabilityLoopSelector, {
      props: {
        kind: 'skill',
        modelValue: [],
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain('workspace-skill');
    expect(wrapper.text()).not.toContain('disabled-skill');

    const select = wrapper.findComponent({ name: 'VSelect' });
    select.vm.$emit('update:modelValue', 'conversation');
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted('update:modelValue')).toEqual([
      [[{ skill_name: 'workspace-skill', loop: 'conversation' }]],
    ]);
    wrapper.unmount();
  });
});

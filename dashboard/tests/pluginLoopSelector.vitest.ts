import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PluginLoopSelector from '@/components/shared/PluginLoopSelector.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  pluginListMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  pluginApi: {
    list: testState.pluginListMock,
  },
}));

describe('PluginLoopSelector', () => {
  beforeEach(() => {
    testState.pluginListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          {
            name: 'example-plugin',
            root_dir_name: 'example-plugin',
            display_name: 'Example Plugin',
            activated: true,
            reserved: false,
          },
          {
            name: 'system-plugin',
            activated: true,
            reserved: true,
          },
        ],
      },
    });
  });

  it('writes only non-default plugin loop assignments', async () => {
    const wrapper = mountWithVuetify(PluginLoopSelector, {
      props: {
        modelValue: [],
      },
    });

    await flushPromises();

    expect(wrapper.text()).toContain('Example Plugin');
    expect(wrapper.text()).not.toContain('system-plugin');

    const select = wrapper.findComponent({ name: 'VSelect' });
    select.vm.$emit('update:modelValue', 'work');
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted('update:modelValue')).toEqual([
      [[{ plugin_id: 'example-plugin', loop: 'work' }]],
    ]);

    await wrapper.setProps({
      modelValue: [{ plugin_id: 'example-plugin', loop: 'work' }],
    });
    select.vm.$emit('update:modelValue', 'both');
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted('update:modelValue')).toEqual([
      [[{ plugin_id: 'example-plugin', loop: 'work' }]],
      [[]],
    ]);
    wrapper.unmount();
  });
});

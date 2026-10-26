import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import PluginSetSelector from '@/components/shared/PluginSetSelector.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const list = vi.fn();

vi.mock('@/api/v1', () => ({
  pluginApi: {
    list: (...args: unknown[]) => list(...args),
  },
}));

describe('PluginSetSelector inline mode', () => {
  beforeEach(() => {
    list.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          {
            name: 'active_plugin',
            activated: true,
            reserved: false,
            display_name: 'Active',
            desc: '',
          },
        ],
      },
    });
  });

  it('preserves configured names that are not in the active plugin list', async () => {
    const wrapper = mountWithVuetify(PluginSetSelector, {
      props: {
        inline: true,
        modelValue: ['inactive_plugin', 'active_plugin'],
      },
    });
    await flushPromises();

    const card = wrapper.find('.inline-plugin-card');
    expect(card.exists()).toBe(true);

    await card.trigger('click');
    let emitted = wrapper.emitted('update:modelValue') ?? [];
    expect(emitted.at(-1)?.[0]).toEqual(['inactive_plugin']);
    await wrapper.setProps({ modelValue: ['inactive_plugin'] });

    await card.trigger('click');
    emitted = wrapper.emitted('update:modelValue') ?? [];
    expect(emitted.at(-1)?.[0]).toEqual(['inactive_plugin', 'active_plugin']);
  });
});

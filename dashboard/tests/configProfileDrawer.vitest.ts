import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConfigProfileDrawer from '@/components/config/ConfigProfileDrawer.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  requestClose: vi.fn(),
}));

vi.mock('@/views/ConfigPage.vue', () => ({
  default: {
    name: 'ConfigPage',
    methods: {
      requestClose: testState.requestClose,
    },
    template:
      '<div class="config-page-stub"><div class="config-panel" /></div>',
  },
}));

describe('ConfigProfileDrawer', () => {
  beforeEach(() => {
    testState.requestClose.mockReset();
  });

  it('keeps the drawer open when the embedded config rejects closing', async () => {
    testState.requestClose.mockResolvedValue(false);
    const wrapper = mountWithVuetify(ConfigProfileDrawer, {
      props: { modelValue: true, configId: 'default' },
    });
    await flushPromises();

    wrapper
      .findComponent({ name: 'VOverlay' })
      .vm.$emit('update:modelValue', false);
    await flushPromises();

    expect(testState.requestClose).toHaveBeenCalledOnce();
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
    wrapper.unmount();
  });

  it('closes only after the embedded config accepts closing', async () => {
    testState.requestClose.mockResolvedValue(true);
    const wrapper = mountWithVuetify(ConfigProfileDrawer, {
      props: { modelValue: true, configId: 'default' },
    });
    await flushPromises();

    wrapper
      .findComponent({ name: 'VOverlay' })
      .vm.$emit('update:modelValue', false);
    await flushPromises();

    expect(wrapper.emitted('update:modelValue')).toEqual([[false]]);
    wrapper.unmount();
  });
});

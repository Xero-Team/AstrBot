import { describe, expect, it } from 'vitest';
import UmoDisplay from '@/components/shared/UmoDisplay.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

describe('UmoDisplay selector layout', () => {
  it('renders the platform logo, raw UMO, and two-line title support', () => {
    const wrapper = mountWithVuetify(UmoDisplay, {
      props: {
        umo: 'qq_official:GroupMessage:1000',
        platformType: 'qq_official',
        autoName: 'Engineering with a deliberately long session name',
        showInfo: false,
        twoLineTitle: true,
      },
    });

    expect(wrapper.classes()).toContain('umo-display--two-line');
    expect(wrapper.find('.platform-logo').exists()).toBe(true);
    expect(wrapper.text()).toContain('Engineering');
    expect(wrapper.text()).toContain('qq_official:GroupMessage:1000');
  });
});

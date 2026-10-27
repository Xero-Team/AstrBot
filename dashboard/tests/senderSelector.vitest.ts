import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import SenderSelector from '@/components/shared/SenderSelector.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  senders: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  conversationApi: { filterOptions: vi.fn() },
  sessionApi: { senders: api.senders },
}));

function mountSelector(modelValue: unknown) {
  return mountWithVuetify(SenderSelector, {
    props: { modelValue },
  });
}

describe('SenderSelector stored values', () => {
  it('renders a non-array plugin value as an empty selection', async () => {
    api.senders.mockResolvedValue({
      data: { status: 'ok', data: { senders: [] } },
    });

    const wrapper = mountSelector(null);
    await flushPromises();

    expect(wrapper.findAll('.sender-chip')).toHaveLength(0);
    wrapper.unmount();
  });

  it('keeps only non-empty string ids from a stored array', async () => {
    api.senders.mockResolvedValue({
      data: { status: 'ok', data: { senders: [] } },
    });

    const wrapper = mountSelector(['  ', 'user-1', null]);
    await flushPromises();

    const chips = wrapper.findAll('.sender-chip');
    expect(chips).toHaveLength(1);
    expect(chips[0]?.text()).toContain('user-1');
    expect(api.senders).toHaveBeenCalledWith({
      sender_ids: ['user-1'],
      limit: 100,
    });
    wrapper.unmount();
  });
});

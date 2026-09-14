import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  getSession: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  chatApi: {
    getSession: api.getSession,
    stopSession: vi.fn(),
  },
  fileApi: {},
}));

import ChatLoadError from '@/components/chat/ChatLoadError.vue';
import { useMessages } from '@/composables/useMessages';

function sessionPage(page: number, hasMore: boolean, ids: string[]) {
  return {
    data: {
      status: 'ok',
      data: {
        history: ids.map((id) => ({
          id,
          content: { type: 'user', message: [{ type: 'plain', text: id }] },
        })),
        page,
        page_size: 2,
        total: 4,
        has_more: hasMore,
        threads: [],
        active_runs: [],
      },
    },
  };
}

describe('chat history pagination', () => {
  beforeEach(() => {
    api.getSession.mockReset();
  });

  it('loads the newest page then prepends earlier messages', async () => {
    api.getSession
      .mockResolvedValueOnce(sessionPage(1, true, ['3', '4']))
      .mockResolvedValueOnce(sessionPage(2, false, ['1', '2']));
    const messages = useMessages({ currentSessionId: ref('s1') });

    await messages.loadSessionMessages('s1');
    expect(messages.activeMessages.value.map((record) => record.id)).toEqual([
      '3',
      '4',
    ]);
    expect(messages.paginationBySession.s1.has_more).toBe(true);

    await messages.loadEarlierMessages('s1');
    expect(messages.activeMessages.value.map((record) => record.id)).toEqual([
      '1',
      '2',
      '3',
      '4',
    ]);
    expect(messages.paginationBySession.s1.has_more).toBe(false);
    expect(api.getSession).toHaveBeenNthCalledWith(1, 's1', {
      page: 1,
      page_size: 50,
    });
    expect(api.getSession).toHaveBeenNthCalledWith(2, 's1', {
      page: 2,
      page_size: 2,
    });
  });

  it('records a load error without dropping already-visible messages', async () => {
    api.getSession
      .mockResolvedValueOnce(sessionPage(1, true, ['3', '4']))
      .mockRejectedValueOnce(new Error('offline'));
    const messages = useMessages({ currentSessionId: ref('s1') });

    await messages.loadSessionMessages('s1');
    await messages.loadEarlierMessages('s1');

    expect(messages.activeMessages.value.map((record) => record.id)).toEqual([
      '3',
      '4',
    ]);
    expect(messages.paginationBySession.s1.error).toContain('offline');
  });

  it('renders a retry action for history load errors', async () => {
    const wrapper = mountWithVuetify(ChatLoadError, {
      props: { message: 'Could not load messages', loading: false },
    });

    expect(wrapper.text()).toContain('Could not load messages');
    await wrapper.get('button').trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
    wrapper.unmount();
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  getSession: vi.fn(),
  updateMessage: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  chatApi: {
    getSession: api.getSession,
    updateMessage: api.updateMessage,
    stopSession: vi.fn(),
  },
  fileApi: {},
}));

import ChatLoadError from '@/components/chat/ChatLoadError.vue';
import { mergeHistoryRecords, useMessages } from '@/composables/useMessages';
import type { ChatRecord } from '@/domain/chat';

function sessionPage(page: number, hasMore: boolean, ids: string[], total = 4) {
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
        total,
        has_more: hasMore,
        threads: [],
        active_runs: [],
      },
    },
  };
}

function record(id: string): ChatRecord {
  return {
    id,
    content: { type: 'user', message: [{ type: 'plain', text: id }] },
  };
}

describe('chat history pagination', () => {
  beforeEach(() => {
    api.getSession.mockReset();
    api.updateMessage.mockReset();
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
    expect(messages.paginationBySession.get('s1')?.has_more).toBe(true);

    await messages.loadEarlierMessages('s1');
    expect(messages.activeMessages.value.map((record) => record.id)).toEqual([
      '1',
      '2',
      '3',
      '4',
    ]);
    expect(messages.paginationBySession.get('s1')?.has_more).toBe(false);
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
    expect(messages.paginationBySession.get('s1')?.error).toContain('offline');
  });

  it('inserts missing history records by numeric id', () => {
    const merged = mergeHistoryRecords(
      [record('51'), record('130')],
      [record('81'), record('40'), record('130')],
    );
    expect(merged.map((item) => String(item.id))).toEqual([
      '40',
      '51',
      '81',
      '130',
    ]);
  });

  it('keeps older pages after truncating and realigning page one', async () => {
    api.getSession
      .mockResolvedValueOnce(sessionPage(1, true, ['101', '150'], 150))
      .mockResolvedValueOnce(sessionPage(2, true, ['51', '100'], 150))
      .mockResolvedValueOnce(sessionPage(1, true, ['81', '130'], 130));
    api.updateMessage.mockResolvedValue({
      data: {
        data: {
          truncated_after_message: true,
          needs_regenerate: true,
          message: {
            id: '100',
            content: {
              type: 'user',
              message: [{ type: 'plain', text: '100' }],
            },
          },
        },
      },
    });
    const messages = useMessages({ currentSessionId: ref('s1') });

    await messages.loadSessionMessages('s1');
    await messages.loadEarlierMessages('s1');
    const edited = messages.activeMessages.value.find(
      (item) => String(item.id) === '100',
    );
    expect(edited).toBeDefined();

    await messages.editMessage('s1', edited as ChatRecord, 'edited');

    expect(
      messages.activeMessages.value.map((item) => String(item.id)),
    ).toEqual(['51', '81', '100', '130']);
    expect(messages.activeMessages.value.includes(edited as ChatRecord)).toBe(
      true,
    );
    expect(messages.paginationBySession.get('s1')).toMatchObject({
      page: 1,
      total: 130,
      has_more: true,
    });
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

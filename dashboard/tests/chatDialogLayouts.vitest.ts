import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ConfigSelector from '@/components/chat/ConfigSelector.vue';
import ProjectDialog from '@/components/chat/ProjectDialog.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  configProfileListMock: vi.fn(),
  configProfileGetMock: vi.fn(),
  configRouteListMock: vi.fn(),
  configRouteUpsertMock: vi.fn(),
  setStoredSelectedChatConfigIdMock: vi.fn(),
  storedConfigId: 'default',
  toastErrorMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  configProfileApi: {
    list: testState.configProfileListMock,
    get: testState.configProfileGetMock,
  },
  configRouteApi: {
    list: testState.configRouteListMock,
    upsert: testState.configRouteUpsertMock,
  },
}));

vi.mock('@/utils/toast', () => ({
  useToast: () => ({
    error: testState.toastErrorMock,
  }),
}));

vi.mock('@/utils/chatConfigBinding', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/utils/chatConfigBinding')>();
  return {
    ...actual,
    getStoredDashboardUsername: () => 'astrbot',
    getStoredSelectedChatConfigId: () => testState.storedConfigId,
    setStoredSelectedChatConfigId: testState.setStoredSelectedChatConfigIdMock,
  };
});

describe('chat dialog layouts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    testState.storedConfigId = 'default';
    testState.configProfileListMock.mockResolvedValue({
      data: {
        data: {
          info_list: [
            { id: 'default', name: 'Default Config' },
            { id: 'agent', name: 'Agent Config' },
          ],
        },
      },
    });
    testState.configProfileGetMock.mockResolvedValue({
      data: {
        data: {
          config: {
            agent_runner: {
              runner_type: 'local',
            },
          },
        },
      },
    });
    testState.configRouteListMock.mockResolvedValue({
      data: {
        data: {
          routing: {},
        },
      },
    });
    testState.configRouteUpsertMock.mockResolvedValue({
      data: {
        status: 'ok',
      },
    });
  });

  it('renders ProjectDialog inside a bounded scroll container', async () => {
    mountWithVuetify(ProjectDialog, {
      props: {
        modelValue: true,
        project: {
          project_id: 'project-1',
          title: 'Long form project',
          emoji: '📁',
          description: Array.from(
            { length: 20 },
            (_, index) => `Line ${index}`,
          ).join('\n'),
          created_at: '2026-06-30T00:00:00Z',
          updated_at: '2026-06-30T00:00:00Z',
        },
      },
    });

    await flushPromises();

    expect(document.body.querySelector('.project-dialog-card')).not.toBeNull();
    expect(
      document.body.querySelector('.project-dialog-card__content'),
    ).not.toBeNull();
  });

  it('renders ConfigSelector inside a bounded scroll container', async () => {
    const wrapper = mountWithVuetify(ConfigSelector, {
      props: {
        sessionId: 'session-1',
        platformId: 'webchat',
      },
    });

    await flushPromises();
    await wrapper.find('.styled-menu-item').trigger('click');
    await flushPromises();

    expect(
      document.body.querySelector('.config-selector-dialog'),
    ).not.toBeNull();
    expect(
      document.body.querySelector('.config-selector-dialog__content'),
    ).not.toBeNull();

    wrapper.unmount();
  });

  it('reconciles to backend routing when the pending bind fails', async () => {
    testState.storedConfigId = 'agent';
    const wrapper = mountWithVuetify(ConfigSelector, {
      props: {
        platformId: 'webchat',
      },
    });
    await flushPromises();

    testState.configRouteUpsertMock.mockRejectedValue(new Error('forbidden'));
    testState.configRouteListMock.mockResolvedValue({
      data: {
        data: {
          routing: {
            'webchat:FriendMessage:webchat!astrbot!session-2':
              'backend-profile',
          },
        },
      },
    });

    await wrapper.setProps({ sessionId: 'session-2' });
    await flushPromises();

    expect(testState.setStoredSelectedChatConfigIdMock).toHaveBeenCalledWith(
      'backend-profile',
    );
    wrapper.unmount();
  });

  it('persists the selection when the pending bind succeeds', async () => {
    testState.storedConfigId = 'agent';
    const wrapper = mountWithVuetify(ConfigSelector, {
      props: {
        platformId: 'webchat',
      },
    });
    await flushPromises();

    await wrapper.setProps({ sessionId: 'session-3' });
    await flushPromises();

    expect(testState.configRouteUpsertMock).toHaveBeenCalledWith(
      'webchat:FriendMessage:webchat!astrbot!session-3',
      { config_id: 'agent' },
    );
    expect(testState.setStoredSelectedChatConfigIdMock).toHaveBeenCalledWith(
      'agent',
    );
    wrapper.unmount();
  });
});

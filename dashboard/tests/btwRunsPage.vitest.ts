import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BtwRunsPage from '@/views/BtwRunsPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const state = vi.hoisted(() => ({
  listMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  btwApi: {
    listWorkSessions: state.listMock,
  },
}));

const SESSION = {
  id: 'session-1',
  config_id: 'default',
  origin: 'webchat:FriendMessage:user',
  request: 'fix the parser',
  task_type: 'work',
  status: 'running',
  created_at: '2026-10-17T00:00:00+00:00',
  updated_at: '2026-10-17T00:00:02+00:00',
  error: null,
  artifacts: ['task-1/report.md'],
  delegations: [
    {
      run_id: 'task-1',
      agent_id: 'codex',
      agent_name: 'Codex',
      agent_type: 'codex',
      workspace: 'task-1',
      status: 'running',
      started_at: '2026-10-17T00:00:01+00:00',
      updated_at: '2026-10-17T00:00:02+00:00',
      finished_at: null,
      latest_action: 'shell: pytest -q',
      event_count: 2,
      tool_call_count: 1,
      exit_code: null,
      detail: '',
      usage: { input_tokens: 10 },
      artifacts: [],
      recent_events: [
        {
          type: 'tool_call',
          timestamp: '2026-10-17T00:00:02+00:00',
          summary: 'shell: pytest -q',
          tool: 'shell',
          status: 'running',
        },
      ],
    },
  ],
};

function mountPage() {
  return mountWithVuetify(BtwRunsPage);
}

describe('BtwRunsPage', () => {
  beforeEach(() => {
    state.listMock.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the empty state when no work session has run', async () => {
    state.listMock.mockResolvedValue({ data: { data: { sessions: [] } } });
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.find('.btw-runs-page__empty').exists()).toBe(true);
    expect(wrapper.text()).toContain('No BTW work session has run yet.');
    wrapper.unmount();
  });

  it('renders delegation progress and its normalized timeline', async () => {
    state.listMock.mockResolvedValue({
      data: { data: { sessions: [SESSION] } },
    });
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain('fix the parser');
    expect(wrapper.text()).toContain('Codex');
    expect(wrapper.text()).toContain('shell: pytest -q');
    expect(wrapper.text()).toContain('2');

    await wrapper.find('.btw-runs-page__timeline-toggle').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('tool_call');
    expect(wrapper.text()).toContain('shell: pytest -q');
    wrapper.unmount();
  });

  it('discovers a task started after the initial empty load', async () => {
    vi.useFakeTimers();
    state.listMock
      .mockResolvedValueOnce({ data: { data: { sessions: [] } } })
      .mockResolvedValueOnce({ data: { data: { sessions: [SESSION] } } });
    const wrapper = mountPage();
    await flushPromises();

    expect(state.listMock).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();

    expect(state.listMock).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('fix the parser');
    wrapper.unmount();
  });

  it('reports a load failure without dropping the page', async () => {
    state.listMock.mockRejectedValue(new Error('offline'));
    const wrapper = mountPage();
    await flushPromises();

    expect(wrapper.text()).toContain('Could not load BTW delegated runs.');
    wrapper.unmount();
  });
});

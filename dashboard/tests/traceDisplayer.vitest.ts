import { flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TraceDisplayer from '@/components/shared/TraceDisplayer.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const state = vi.hoisted(() => ({
  history: vi.fn(),
  detail: vi.fn(),
  plugins: vi.fn(),
  sessions: vi.fn(),
  sources: [] as Array<{
    close: ReturnType<typeof vi.fn>;
    onerror: (() => void) | null;
  }>,
}));

vi.mock('@/api/v1', () => ({
  logApi: {
    liveUrl: () => '/api/v1/logs/live',
  },
  traceApi: {
    history: state.history,
    detail: state.detail,
  },
  pluginApi: {
    getAll: state.plugins,
  },
  sessionApi: {
    activeUmos: state.sessions,
  },
}));

vi.mock('event-source-polyfill', () => ({
  EventSourcePolyfill: class {
    close = vi.fn();
    onerror: (() => void) | null = null;

    constructor() {
      state.sources.push(this);
    }
  },
}));

describe('TraceDisplayer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.sources.splice(0);
    state.history.mockResolvedValue({
      data: {
        status: 'ok',
        data: { traces: [], total: 0, page: 1, storage: {} },
      },
    });
    state.plugins.mockResolvedValue({ data: { data: [] } });
    state.sessions.mockResolvedValue({ data: { data: { umo_infos: [] } } });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('cancels a scheduled SSE reconnect when the displayer is unmounted', async () => {
    vi.useFakeTimers();
    const wrapper = mountWithVuetify(TraceDisplayer);
    await flushPromises();

    expect(state.history).toHaveBeenCalled();
    expect(state.sources).toHaveLength(1);

    state.sources[0]!.onerror?.();
    expect(state.sources[0]!.close).toHaveBeenCalledOnce();

    wrapper.unmount();
    await vi.runAllTimersAsync();

    expect(state.sources).toHaveLength(1);
  });

  it('renders table chrome from the trace catalog', async () => {
    const wrapper = mountWithVuetify(TraceDisplayer);
    await flushPromises();

    expect(wrapper.text()).toContain('Status');
    expect(wrapper.text()).toContain('Platform');
    expect(wrapper.text()).toContain('Timestamp');
    expect(wrapper.text()).toContain('Message');
    expect(wrapper.text()).toContain('UMO');
    expect(wrapper.text()).toContain('Sender');
    expect(wrapper.text()).toContain('Spans');
    expect(wrapper.text()).toContain('No trace data yet');
  });

  it('renders a legacy persona_id trace field as a Prompt chip', async () => {
    mockAgentPrepareTrace('persona_id', 'legacy-persona');

    const wrapper = await mountTraceDetail();

    expect(wrapper.text()).toContain('legacy-persona');
    expect(promptChipTitles(wrapper)).toContain('Prompt: legacy-persona');
  });

  it('renders a prompt_id trace field recorded by new traces', async () => {
    mockAgentPrepareTrace('prompt_id', 'new-prompt');

    const wrapper = await mountTraceDetail();

    expect(wrapper.text()).toContain('new-prompt');
    expect(wrapper.text()).not.toContain('persona');
    expect(promptChipTitles(wrapper)).toContain('Prompt: new-prompt');
  });
});

function mockAgentPrepareTrace(
  field: 'persona_id' | 'prompt_id',
  value: string,
) {
  state.history.mockResolvedValue({
    data: {
      status: 'ok',
      data: {
        traces: [
          {
            trace_id: 'trace-detail',
            name: 'AstrMessageEvent',
            attributes: {},
            state: 'ended',
            start_time_unix_nano: '1000000000',
            end_time_unix_nano: '2000000000',
            span_count: 2,
          },
        ],
        total: 1,
        page: 1,
        storage: {},
      },
    },
  });
  state.detail.mockResolvedValue({
    data: {
      status: 'ok',
      data: {
        trace: {
          trace_id: 'trace-detail',
          name: 'AstrMessageEvent',
          attributes: {},
          state: 'ended',
          start_time_unix_nano: '1000000000',
          end_time_unix_nano: '2000000000',
          span_count: 2,
        },
        spans: [
          {
            span_id: 'root-span',
            parent_span_id: '',
            name: 'AstrMessageEvent',
            attributes: {},
            start_time_unix_nano: '1000000000',
            end_time_unix_nano: '2000000000',
            events: [],
          },
          {
            span_id: 'agent-span',
            parent_span_id: 'root-span',
            name: 'Agent',
            attributes: { 'astrbot.kind': 'agent' },
            start_time_unix_nano: '1100000000',
            end_time_unix_nano: '1900000000',
            events: [
              {
                event_id: 'prepare-event',
                span_id: 'agent-span',
                name: 'astr_agent_prepare',
                time_unix_nano: '1200000000',
                attributes: { [`astrbot.${field}`]: value },
              },
            ],
          },
        ],
      },
    },
  });
}

async function mountTraceDetail() {
  const wrapper = mountWithVuetify(TraceDisplayer);
  await flushPromises();

  await wrapper.find('.trace-list-row').trigger('click');
  await flushPromises();
  return wrapper;
}

function promptChipTitles(wrapper: ReturnType<typeof mountWithVuetify>) {
  return wrapper
    .findAll('.timeline-metadata-chip')
    .map((chip) => chip.attributes('title'))
    .filter((title): title is string => Boolean(title));
}

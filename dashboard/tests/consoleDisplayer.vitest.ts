import { readFile } from 'node:fs/promises';
import { flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const api = vi.hoisted(() => ({
  history: vi.fn(),
  pluginList: vi.fn(),
  eventSources: [] as Array<Record<string, unknown>>,
}));

vi.mock('@/api/v1', () => ({
  logApi: {
    history: () => api.history(),
    liveUrl: () => '/api/v1/logs/live',
  },
  pluginApi: {
    list: () => api.pluginList(),
  },
}));

vi.mock('event-source-polyfill', () => {
  class FakeEventSource {
    onopen: (() => void) | null = null;
    onmessage: ((event: MessageEvent<string>) => void) | null = null;
    onerror: ((event: unknown) => void) | null = null;

    constructor() {
      api.eventSources.push(this);
    }

    close() {}
  }

  return { EventSourcePolyfill: FakeEventSource };
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

afterEach(() => {
  vi.useRealTimers();
  api.history.mockReset();
  api.pluginList.mockReset();
  api.eventSources.length = 0;
});

describe('ConsoleDisplayer stream lifecycle', () => {
  it('stops mount work when unmounted during history loading', async () => {
    const history = deferred<unknown>();
    api.history.mockReturnValue(history.promise);
    api.pluginList.mockResolvedValue({ data: { data: [] } });

    const wrapper = mountWithVuetify(ConsoleDisplayer, {
      props: { workspaceMode: true },
    });
    await Promise.resolve();
    wrapper.unmount();
    history.resolve({ data: { data: { logs: [] } } });
    await flushPromises();

    expect(api.pluginList).not.toHaveBeenCalled();
    expect(api.eventSources).toHaveLength(0);
  });

  it('does not attach lifecycle listeners when unmounted during plugin loading', async () => {
    api.history.mockResolvedValueOnce({ data: { data: { logs: [] } } });
    const plugins = deferred<unknown>();
    api.pluginList.mockReturnValue(plugins.promise);
    const addListener = vi.spyOn(document, 'addEventListener');

    const wrapper = mountWithVuetify(ConsoleDisplayer, {
      props: { workspaceMode: true },
    });
    await flushPromises();
    wrapper.unmount();
    plugins.resolve({ data: { data: [] } });
    await flushPromises();

    const fullscreenAdds = addListener.mock.calls.filter(
      ([type]) => type === 'fullscreenchange',
    );
    expect(fullscreenAdds).toHaveLength(0);
    expect(api.eventSources).toHaveLength(0);
  });

  it('does not open a stream when a pending reconnect finishes after unmount', async () => {
    vi.useFakeTimers();
    api.history.mockResolvedValueOnce({ data: { data: { logs: [] } } });
    const reconnect = deferred<unknown>();
    api.pluginList.mockResolvedValue({ data: { data: [] } });

    const wrapper = mountWithVuetify(ConsoleDisplayer, {
      props: { workspaceMode: true },
    });
    await flushPromises();
    expect(api.eventSources).toHaveLength(1);

    api.history.mockReturnValue(reconnect.promise);
    const source = api.eventSources[0] as {
      onerror?: (event: unknown) => void;
    };
    source.onerror?.({});
    await vi.advanceTimersByTimeAsync(1000);
    wrapper.unmount();
    reconnect.resolve({ data: { data: { logs: [] } } });
    await flushPromises();

    expect(api.eventSources).toHaveLength(1);
  });
});

describe('ConsoleDisplayer log rendering', () => {
  it('batches DOM insertion and keeps log content text-only', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain('document.createDocumentFragment()');
    expect(source).toContain('target.appendChild(fragment)');
    expect(source).toContain('element.textContent = cleanText');
    expect(source).toContain('highlight.textContent = cleanText.slice');
    expect(source).not.toContain('innerHTML = log');
  });

  it('filters logs with a debounced, localized search field', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain("useModuleI18n('features/logs')");
    expect(source).toContain('matchesKeyword(log)');
    expect(source).toContain('searchTimer.value = window.setTimeout');
    expect(source).toContain("tm('search.placeholder')");
  });

  it('intersects level, source, plugin, and platform filters', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain('matchesSource(log)');
    expect(source).toContain('matchesPlugin(log)');
    expect(source).toContain('matchesPlatform(log)');
    expect(source).toContain("selectedPlatform.value === '__unscoped__'");
    expect(source).toContain("tm('filters.button')");
    expect(source).toContain("tm('filters.unscopedPlatform')");
  });

  it('labels the plugin filter as current-log sources with an explicit hint', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain("tm('filters.pluginsInLogs')");
    expect(source).toContain("tm('filters.pluginsInLogsHint')");
    expect(source).not.toContain("tm('filters.allPlugins')");
  });

  it('builds plugin filter options only from retained logs', async () => {
    api.history.mockResolvedValue({
      data: {
        data: {
          logs: [
            {
              time: 1,
              level: 'INFO',
              data: 'cached',
              plugin_name: 'uninstalled',
            },
          ],
        },
      },
    });
    api.pluginList.mockResolvedValue({
      data: { data: [{ name: 'weather', display_name: 'Weather Forecast' }] },
    });

    const wrapper = mountWithVuetify(ConsoleDisplayer, {
      props: { workspaceMode: true },
    });
    await flushPromises();

    const filterButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Filters'));
    await filterButton?.trigger('click');

    const pluginSelect = wrapper.findAllComponents({ name: 'VSelect' })[0];
    const items = pluginSelect.props('items') as Array<{
      title: string;
      value: string;
    }>;
    expect(items.map((item) => item.value)).toEqual(['uninstalled']);
    expect(items.map((item) => item.title)).toEqual(['uninstalled']);
  });

  it('prefers plugin display names while keeping ids as values', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain('pluginDisplayNames.value[value] || value');
    expect(source).toContain('subtitle: value');
    expect(source).toContain('pluginApi.list()');
  });

  it('applies the configurable log font size', async () => {
    const source = await readFile(
      'src/components/shared/ConsoleDisplayer.vue',
      'utf8',
    );

    expect(source).toContain('--console-log-font-size');
  });
});

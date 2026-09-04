import { describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { ref } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import MarketPluginsTab from '@/views/extension/MarketPluginsTab.vue';
import { EXTENSION_DETAILS_ROUTE_NAME } from '@/router/routeConstants';
import {
  getMarketPluginId,
  indexMarketPluginsById,
  isMarketMetaKey,
  marketPluginIdFields,
  readRoutePluginId,
  resolveSelectedMarketPlugin,
  toRoutePluginIdParam,
} from '@/utils/marketPluginKey';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('@/components/extension/MarketPluginCard.vue', () => ({
  default: {
    props: ['plugin'],
    template:
      '<button class="market-plugin-card-stub" type="button" @click="$emit(\'open\', plugin)">{{ plugin.author }}</button>',
  },
}));

vi.mock('@/components/extension/PluginSortControl.vue', () => ({
  default: {
    props: ['modelValue', 'items', 'label', 'order'],
    template: '<div class="plugin-sort-control-stub">{{ label }}</div>',
  },
}));

const sameNamedPlugins = [
  {
    name: 'weather',
    author: 'alice',
    repo: 'https://github.com/alice/weather',
    version: '1.0.0',
  },
  {
    name: 'weather',
    author: 'bob',
    repo: 'https://github.com/bob/weather',
    version: '2.0.0',
  },
];

describe('getMarketPluginId', () => {
  it('uses author/name and prefers an explicit runtime market_plugin_id', () => {
    expect(isMarketMetaKey('$meta')).toBe(true);
    expect(
      getMarketPluginId({
        market_plugin_id: '  alice/weather  ',
        author: 'ignored',
        name: 'ignored',
      }),
    ).toBe('alice/weather');
    expect(
      getMarketPluginId({
        author: 'alice',
        name: 'weather',
        repo: 'https://github.com/alice/weather',
      }),
    ).toBe('alice/weather');
    expect(
      getMarketPluginId({
        repo: 'https://github.com/a/b',
        name: 'dup',
      }),
    ).toBe('');
    expect(getMarketPluginId({ name: 'dup' })).toBe('');
    expect(getMarketPluginId({})).toBe('');
  });

  it('gives same-named plugins distinct author/name keys', () => {
    expect(getMarketPluginId(sameNamedPlugins[0])).toBe('alice/weather');
    expect(getMarketPluginId(sameNamedPlugins[1])).toBe('bob/weather');
  });
});

describe('readRoutePluginId', () => {
  it('joins array segments so author/name is not truncated to author', () => {
    expect(readRoutePluginId('bob/weather')).toBe('bob/weather');
    expect(readRoutePluginId(['bob', 'weather'])).toBe('bob/weather');
    expect(readRoutePluginId(['  bob/weather  '])).toBe('bob/weather');
    expect(readRoutePluginId(['', 'bob', 'weather'])).toBe('bob/weather');
    expect(readRoutePluginId(undefined)).toBe('');
    expect(toRoutePluginIdParam('bob/weather')).toEqual(['bob', 'weather']);
    expect(toRoutePluginIdParam('weather')).toEqual(['weather']);
  });
});

describe('marketPluginIdFields', () => {
  it('adds market_plugin_id only when author/name can be resolved', () => {
    expect(marketPluginIdFields(sameNamedPlugins[1])).toEqual({
      market_plugin_id: 'bob/weather',
    });
    expect(marketPluginIdFields({ name: 'weather' })).toEqual({});
    expect(marketPluginIdFields(null)).toEqual({});
  });
});

describe('indexMarketPluginsById', () => {
  it('skips records that cannot form an author/name id', () => {
    const indexed = indexMarketPluginsById([
      ...sameNamedPlugins,
      { name: 'orphan' },
      { author: 'carol' },
    ]);
    expect([...indexed.keys()]).toEqual(['alice/weather', 'bob/weather']);
    expect(indexed.get('')).toBeUndefined();
  });
});

describe('resolveSelectedMarketPlugin', () => {
  it('resolves market details by plugin_id instead of the first shared name', () => {
    expect(
      resolveSelectedMarketPlugin(
        sameNamedPlugins,
        'bob/weather',
        'market',
        null,
      )?.author,
    ).toBe('bob');
    expect(
      resolveSelectedMarketPlugin(sameNamedPlugins, 'weather', 'market', null),
    ).toBeNull();
  });

  it('matches installed details by the installed plugin_id, not repo or name', () => {
    expect(
      resolveSelectedMarketPlugin(sameNamedPlugins, 'weather', 'installed', {
        name: 'weather',
        author: 'bob',
        repo: 'https://github.com/alice/weather',
      })?.author,
    ).toBe('bob');
  });
});

describe('ExtensionDetails route', () => {
  it('keeps author/name as one pluginId and does not steal plugin page routes', async () => {
    const Stub = { template: '<div />' };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/extension/:extensionId/pages/:pageId',
          name: 'PluginPageHost',
          component: Stub,
        },
        {
          path: '/extension/:pluginId+',
          name: EXTENSION_DETAILS_ROUTE_NAME,
          component: Stub,
        },
      ],
    });

    await router.push({
      name: EXTENSION_DETAILS_ROUTE_NAME,
      params: { pluginId: toRoutePluginIdParam('bob/weather') },
      hash: '#market',
    });
    expect(router.currentRoute.value.path).toBe('/extension/bob/weather');
    expect(readRoutePluginId(router.currentRoute.value.params.pluginId)).toBe(
      'bob/weather',
    );

    await router.push('/extension/alice/pages/home');
    expect(router.currentRoute.value.name).toBe('PluginPageHost');
    expect(router.currentRoute.value.params).toMatchObject({
      extensionId: 'alice',
      pageId: 'home',
    });
  });
});

describe('MarketPluginsTab', () => {
  it('opens same-named market plugins with author/name route ids', async () => {
    const push = vi.fn();
    const wrapper = mountWithVuetify(MarketPluginsTab, {
      props: {
        state: {
          tm: (key: string) => key,
          router: { push },
          activeTab: ref('market'),
          pluginMarketData: ref(sameNamedPlugins),
          loading_: ref(false),
          currentPage: ref(1),
          customSources: ref([]),
          selectedSource: ref(null),
          showPluginFullName: ref(false),
          marketSearch: ref(''),
          refreshingMarket: ref(false),
          sortBy: ref('default'),
          sortOrder: ref('desc'),
          marketCategoryFilter: ref('all'),
          marketCategoryItems: ref([]),
          randomPlugins: ref([]),
          refreshRandomPlugins: vi.fn(),
          totalPages: ref(1),
          paginatedPlugins: ref(sameNamedPlugins),
          openInstallDialog: vi.fn(),
          handleInstallPlugin: vi.fn(),
          openSourceManagerDialog: vi.fn(),
          refreshPluginMarket: vi.fn(),
        },
      },
    });

    await flushPromises();
    const cards = wrapper.findAll('.market-plugin-card-stub');
    expect(cards).toHaveLength(2);
    await cards[1].trigger('click');
    expect(push).toHaveBeenCalledWith({
      name: 'ExtensionDetails',
      params: { pluginId: ['bob', 'weather'] },
      hash: '#market',
    });
    wrapper.unmount();
  });
});

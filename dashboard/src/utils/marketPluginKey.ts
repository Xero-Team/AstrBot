export const MARKET_META_KEY = '$meta';

export interface MarketPluginIdentity {
  market_plugin_id?: unknown;
  author?: unknown;
  name?: unknown;
  install_source?: unknown;
}

const readTrimmedString = (value: unknown): string =>
  typeof value === 'string' ? value.trim() : '';

const readNestedMarketPluginId = (plugin: MarketPluginIdentity): string => {
  const source = plugin.install_source;
  if (!source || typeof source !== 'object') {
    return '';
  }
  return readTrimmedString(
    (source as { market_plugin_id?: unknown }).market_plugin_id,
  );
};

export const isMarketMetaKey = (key: string): boolean =>
  key === MARKET_META_KEY;

const getPluginAuthor = (
  plugin: MarketPluginIdentity | null | undefined,
): string => readTrimmedString(plugin?.author);

const getPluginName = (
  plugin: MarketPluginIdentity | null | undefined,
): string => readTrimmedString(plugin?.name);

export const getMarketPluginId = (
  plugin: MarketPluginIdentity | null | undefined,
): string => {
  if (!plugin) {
    return '';
  }
  const explicit =
    readTrimmedString(plugin.market_plugin_id) ||
    readNestedMarketPluginId(plugin);
  if (explicit) {
    return explicit;
  }
  const author = getPluginAuthor(plugin);
  const name = getPluginName(plugin);
  if (author && name) {
    return `${author}/${name}`;
  }
  return '';
};

export const readRoutePluginId = (pluginId: unknown): string => {
  if (Array.isArray(pluginId)) {
    return pluginId
      .map((part) => (typeof part === 'string' ? part.trim() : ''))
      .filter(Boolean)
      .join('/');
  }
  return typeof pluginId === 'string' ? pluginId.trim() : '';
};

export const toRoutePluginIdParam = (pluginId: string): string[] =>
  pluginId
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean);

export const marketPluginIdFields = (
  plugin: MarketPluginIdentity | null | undefined,
): { market_plugin_id: string } | Record<string, never> => {
  const marketPluginId = getMarketPluginId(plugin);
  if (!marketPluginId) {
    return {};
  }
  return { market_plugin_id: marketPluginId };
};

export const indexMarketPluginsById = <T extends MarketPluginIdentity>(
  plugins: readonly T[],
): Map<string, T> => {
  const indexed = new Map<string, T>();
  for (const plugin of plugins) {
    const id = getMarketPluginId(plugin);
    if (id) {
      indexed.set(id, plugin);
    }
  }
  return indexed;
};

export const resolveSelectedMarketPlugin = <T extends MarketPluginIdentity>(
  market: readonly T[],
  selectedPluginId: string,
  selectedDetailTab: string,
  installedPlugin: MarketPluginIdentity | null | undefined,
): T | null => {
  const selected = selectedPluginId.trim();
  if (!selected) {
    return null;
  }

  const byPluginId =
    market.find((item) => getMarketPluginId(item) === selected) ?? null;

  if (selectedDetailTab === 'market' || !installedPlugin) {
    return byPluginId;
  }

  const installedId = getMarketPluginId(installedPlugin);
  if (!installedId) {
    return null;
  }
  return market.find((item) => getMarketPluginId(item) === installedId) ?? null;
};

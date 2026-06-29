import { useI18n } from '@/i18n/composables';

type I18nMap = Record<string, unknown>;

interface PluginLike {
  name?: string;
  display_name?: string;
  desc?: string;
  description?: string;
  short_desc?: string;
  i18n?: I18nMap;
}

interface PluginPageLike {
  i18n_key?: string;
  page_name?: string;
  name?: string;
  title?: string;
  description?: string;
  desc?: string;
}

function getLocaleData(i18n: unknown, locale: string): I18nMap | null {
  if (!i18n || typeof i18n !== 'object' || !locale) return null;
  const source = i18n as Record<string, unknown>;
  const localeData = source[locale];
  return localeData && typeof localeData === 'object'
    ? (localeData as I18nMap)
    : null;
}

function getByPath(source: unknown, key: string): unknown {
  if (!source || typeof source !== 'object' || !key) return undefined;

  const parts = key.split('.');
  let current: unknown = source;
  for (const part of parts) {
    if (!current || typeof current !== 'object' || !(part in current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

export function resolvePluginI18n(
  i18n: unknown,
  locale: string,
  key: string,
  fallback = '',
): string {
  const localeData = getLocaleData(i18n, locale);
  const value = getByPath(localeData, key);
  return value === undefined || value === null ? fallback : String(value);
}

function getPluginPageI18nBase(
  page: PluginPageLike | string | null | undefined,
) {
  if (page && typeof page === 'object') {
    if (typeof page.i18n_key === 'string' && page.i18n_key.trim()) {
      return page.i18n_key.trim();
    }
    const pageName = page.page_name || page.name;
    return pageName ? `pages.${pageName}` : '';
  }

  return page ? `pages.${page}` : '';
}

export function usePluginI18n() {
  const { locale } = useI18n();

  const resolve = (i18n: unknown, key: string, fallback = '') => {
    return resolvePluginI18n(i18n, locale.value, key, fallback);
  };

  const pluginName = (plugin: PluginLike): string => {
    const fallback = plugin?.display_name?.length
      ? plugin.display_name
      : plugin?.name;
    return resolve(plugin?.i18n, 'metadata.display_name', fallback || '');
  };

  const pluginDesc = (plugin: PluginLike, fallback = ''): string => {
    return resolve(
      plugin?.i18n,
      'metadata.desc',
      fallback || plugin?.desc || plugin?.description || '',
    );
  };

  const pluginShortDesc = (plugin: PluginLike, fallback = ''): string => {
    return resolve(
      plugin?.i18n,
      'metadata.short_desc',
      fallback ||
        plugin?.short_desc ||
        plugin?.desc ||
        plugin?.description ||
        '',
    );
  };

  const pluginPageText = (
    plugin: PluginLike,
    page: PluginPageLike | string | null | undefined,
    attr: string,
    fallback = '',
  ): string => {
    const base = getPluginPageI18nBase(page);
    if (!base || !attr) {
      return fallback;
    }
    return resolve(plugin?.i18n, `${base}.${attr}`, fallback);
  };

  const pluginPageTitle = (
    plugin: PluginLike,
    page: PluginPageLike | string | null | undefined,
    fallback = '',
  ): string => {
    const pageFallback =
      fallback ||
      (page && typeof page === 'object'
        ? page.title || page.name || page.page_name
        : page) ||
      '';
    return pluginPageText(plugin, page, 'title', pageFallback);
  };

  const pluginPageDescription = (
    plugin: PluginLike,
    page: PluginPageLike | string | null | undefined,
    fallback = '',
  ): string => {
    const pageFallback =
      fallback ||
      (page && typeof page === 'object' ? page.description || page.desc : '') ||
      '';
    return pluginPageText(plugin, page, 'description', pageFallback);
  };

  const configText = (
    i18n: unknown,
    path: string,
    attr: string,
    fallback = '',
  ): string => {
    const key = path ? `config.${path}.${attr}` : `config.${attr}`;
    return resolve(i18n, key, fallback);
  };

  return {
    locale,
    resolve,
    pluginName,
    pluginDesc,
    pluginShortDesc,
    pluginPageText,
    pluginPageTitle,
    pluginPageDescription,
    configText,
  };
}

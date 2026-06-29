import { pinyin } from 'pinyin-pro';

const HAN_IDEOGRAPH_RE = /\p{Unified_Ideograph}/u;

export interface SearchQuery {
  norm: string;
  loose: string;
}

export interface SearchablePlugin {
  name?: string;
  trimmedName?: string;
  display_name?: string;
  short_desc?: string;
  desc?: string;
  author?: unknown;
  repo?: string;
  version?: string;
  astrbot_version?: string;
  support_platforms?: string[];
  tags?: string[];
}

export const normalizeStr = (s: unknown): string =>
  (s ?? '').toString().toLowerCase().trim();

const normalizeLooseFromNormalized = (normalized: string): string =>
  normalized.replace(/[\s_-]+/g, '').replace(/[()（）【】\[\]{}·•]+/g, '');

export const normalizeLoose = (s: unknown): string =>
  normalizeLooseFromNormalized(normalizeStr(s));

const memoizeStringFn = <T>(fn: (value: string) => T) => {
  const cache = new Map<string, T>();

  return (raw: unknown): T => {
    const key = (raw ?? '').toString();
    const cached = cache.get(key);
    if (cached !== undefined) {
      return cached;
    }

    const value = fn(key);
    cache.set(key, value);
    return value;
  };
};

const getNormalizedText = memoizeStringFn(normalizeStr);

const getLooseText = memoizeStringFn((text) =>
  normalizeLooseFromNormalized(getNormalizedText(text)),
);

export const toPinyinText = memoizeStringFn((text) =>
  pinyin(text, { toneType: 'none' }).toLowerCase().replace(/\s+/g, ''),
);

export const toInitials = memoizeStringFn((text) =>
  pinyin(text, { pattern: 'first', toneType: 'none' })
    .toLowerCase()
    .replace(/\s+/g, ''),
);

export const buildSearchQuery = (raw: unknown): SearchQuery | null => {
  const norm = getNormalizedText(raw);
  if (!norm) return null;
  return {
    norm,
    loose: getLooseText(raw),
  };
};

export const matchesText = (
  value: unknown,
  query: SearchQuery | null | undefined,
): boolean => {
  if (value === null || value === undefined || !query?.norm) return false;
  const text = String(value);

  const normalizedValue = getNormalizedText(text);
  const looseValue = query.loose ? getLooseText(text) : null;

  if (normalizedValue.includes(query.norm)) return true;
  if (query.loose && looseValue?.includes(query.loose)) return true;

  if (!HAN_IDEOGRAPH_RE.test(text)) return false;

  const pinyinValue = toPinyinText(text);
  if (pinyinValue.includes(query.norm)) return true;

  const initialsValue = toInitials(text);
  if (initialsValue.includes(query.norm)) return true;

  return false;
};

export const getPluginSearchFields = (plugin: SearchablePlugin): unknown[] => {
  const supportPlatforms = Array.isArray(plugin.support_platforms)
    ? plugin.support_platforms.join(' ')
    : '';
  const tags = Array.isArray(plugin.tags) ? plugin.tags.join(' ') : '';

  return [
    plugin.name,
    plugin.trimmedName,
    plugin.display_name,
    plugin.short_desc,
    plugin.desc,
    plugin.author,
    plugin.repo,
    plugin.version,
    plugin.astrbot_version,
    supportPlatforms,
    tags,
  ];
};

export const matchesPluginSearch = (
  plugin: SearchablePlugin,
  query: SearchQuery | null,
): boolean => {
  if (!query) return true;

  return getPluginSearchFields(plugin).some((candidate) =>
    matchesText(candidate, query),
  );
};

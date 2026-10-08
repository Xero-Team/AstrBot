type TranslationTree = Record<string, unknown>;

type Locale = 'zh-CN' | 'en-US';

const localeModules = import.meta.glob('./locales/*/**/*.json', {
  import: 'default',
});

function addModule(
  translations: TranslationTree,
  modulePath: string,
  value: unknown,
) {
  const parts = modulePath.replace(/\.json$/, '').split('/');
  if (parts[0] === 'features' && parts[1] === 'tool-use') {
    parts[1] = 'tooluse';
  }

  let target = translations;
  for (const part of parts.slice(0, -1)) {
    const current = target[part];
    if (!current || typeof current !== 'object') {
      target[part] = {};
    }
    target = target[part] as TranslationTree;
  }
  target[parts.at(-1)!] = value;
}

async function loadLocale(locale: Locale): Promise<TranslationTree> {
  const prefix = `./locales/${locale}/`;
  const entries = Object.entries(localeModules).filter(([path]) =>
    path.startsWith(prefix),
  );
  const loaded = await Promise.all(
    entries.map(async ([path, load]) => [path, await load()] as const),
  );
  const translations: TranslationTree = {};
  for (const [path, value] of loaded) {
    addModule(translations, path.slice(prefix.length), value);
  }
  return translations;
}

export const localeLoaders: Record<Locale, () => Promise<TranslationTree>> = {
  'zh-CN': () => loadLocale('zh-CN'),
  'en-US': () => loadLocale('en-US'),
};

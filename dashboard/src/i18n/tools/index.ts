// 导出核心组件
export { I18nValidator } from '../validator';
export { I18nLoader } from '../loader';
export type * from '../types';

type TranslationTree = Record<string, unknown>;

// 实用工具函数
export function generateMissingKeys(
  sourceTranslations: TranslationTree,
  targetTranslations: TranslationTree,
): string[] {
  const missing: string[] = [];

  function traverse(
    source: TranslationTree,
    target: TranslationTree,
    path: string = '',
  ) {
    for (const key in source) {
      const currentPath = path ? `${path}.${key}` : key;

      if (typeof source[key] === 'object' && source[key] !== null) {
        if (!target[key]) {
          missing.push(currentPath);
        } else {
          traverse(
            source[key] as TranslationTree,
            target[key] as TranslationTree,
            currentPath,
          );
        }
      } else if (!(key in target)) {
        missing.push(currentPath);
      }
    }
  }

  traverse(sourceTranslations, targetTranslations);
  return missing;
}

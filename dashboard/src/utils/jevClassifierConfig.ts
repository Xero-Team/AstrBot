export type JevClassifierValidationKey = 'https' | 'key' | 'model' | 'timeout';

type JevClassifierConfig = Record<string, unknown>;

export function isJevClassifierConfig(config: JevClassifierConfig): boolean {
  return config.type === 'jev_systemone';
}

export function validateJevClassifierConfig(
  config: JevClassifierConfig,
): JevClassifierValidationKey | null {
  if (!isJevClassifierConfig(config)) return null;

  const apiBase = String(config.api_base || '').trim();
  if (!apiBase.startsWith('https://')) return 'https';

  const keys = Array.isArray(config.key)
    ? config.key.filter((key) => String(key || '').trim())
    : [];
  if (keys.length === 0) return 'key';

  if (!String(config.model || '').trim()) return 'model';

  const timeout = Number(config.timeout);
  if (!Number.isFinite(timeout) || timeout <= 0) return 'timeout';

  return null;
}

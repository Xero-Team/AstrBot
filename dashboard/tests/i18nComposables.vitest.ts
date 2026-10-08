import { afterEach, describe, expect, it, vi } from 'vitest';
import { initI18n, useI18n } from '@/i18n/composables';
import { localeLoaders } from '@/i18n/localeLoader';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('i18n locale loading', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('ignores a stale locale request after the user switches back', async () => {
    await initI18n('zh-CN');
    const pendingEnglish = deferred<Record<string, unknown>>();
    const localeChanged = vi.fn();
    window.addEventListener('astrbot-locale-changed', localeChanged);
    vi.spyOn(localeLoaders, 'en-US').mockReturnValue(pendingEnglish.promise);

    const staleRequest = useI18n().setLocale('en-US');
    await useI18n().setLocale('zh-CN');
    pendingEnglish.resolve({ core: { common: { confirm: 'Confirm' } } });
    await staleRequest;

    expect(useI18n().locale.value).toBe('zh-CN');
    expect(localStorage.getItem('astrbot-locale')).toBeNull();
    expect(localeChanged).not.toHaveBeenCalled();
    window.removeEventListener('astrbot-locale-changed', localeChanged);
  });

  it('uses the fallback locale for state, storage, and events', async () => {
    await initI18n('zh-CN');
    const localeChanged = vi.fn();
    window.addEventListener('astrbot-locale-changed', localeChanged);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(localeLoaders, 'en-US').mockRejectedValue(
      new Error('English chunk unavailable'),
    );
    vi.spyOn(localeLoaders, 'zh-CN').mockResolvedValue({
      core: { common: { confirm: '确认' } },
    });

    await useI18n().setLocale('en-US');

    expect(useI18n().locale.value).toBe('zh-CN');
    expect(localStorage.getItem('astrbot-locale')).toBe('zh-CN');
    expect(localeChanged).toHaveBeenCalledWith(
      expect.objectContaining({ detail: { locale: 'zh-CN' } }),
    );
    window.removeEventListener('astrbot-locale-changed', localeChanged);
  });

  it('propagates an error when the fallback locale also cannot load', async () => {
    await initI18n('zh-CN');
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(localeLoaders, 'en-US').mockRejectedValue(
      new Error('English chunk unavailable'),
    );
    vi.spyOn(localeLoaders, 'zh-CN').mockRejectedValue(
      new Error('Chinese chunk unavailable'),
    );

    await expect(initI18n('en-US')).rejects.toThrow(
      'Chinese chunk unavailable',
    );
  });
});

import { afterEach, beforeEach, vi } from 'vitest';
import { initI18n } from '@/i18n/composables';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class IntersectionObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

const localStorageMock = (() => {
  const store = new Map<string, string>();

  return {
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
    get length() {
      return store.size;
    },
  };
})();

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: localStorageMock,
});

Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: localStorageMock,
});

if (!window.visualViewport) {
  Object.defineProperty(window, 'visualViewport', {
    configurable: true,
    value: {
      width: window.innerWidth,
      height: window.innerHeight,
      offsetTop: 0,
      offsetLeft: 0,
      scale: 1,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
  });
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = ResizeObserverMock as typeof ResizeObserver;
}

if (!globalThis.IntersectionObserver) {
  globalThis.IntersectionObserver =
    IntersectionObserverMock as typeof IntersectionObserver;
}

function evaluateMediaQuery(query: string): boolean {
  const minWidth = /min-width:\s*([\d.]+)px/.exec(query);
  const maxWidth = /max-width:\s*([\d.]+)px/.exec(query);
  if (!minWidth && !maxWidth) {
    return false;
  }
  const width = window.innerWidth;
  return (
    (!minWidth || width >= Number(minWidth[1])) &&
    (!maxWidth || width <= Number(maxWidth[1]))
  );
}

Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: evaluateMediaQuery(query),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

if (!window.CSS) {
  Object.defineProperty(window, 'CSS', {
    configurable: true,
    value: { supports: () => false },
  });
} else if (!window.CSS.supports) {
  window.CSS.supports = () => false;
}

if (!document.createRange) {
  document.createRange = () =>
    ({
      setStart: () => {},
      setEnd: () => {},
      commonAncestorContainer: document.body,
    }) as Range;
}

if (!document.queryCommandSupported) {
  document.queryCommandSupported = () => false;
}

Object.defineProperty(Element.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(Element.prototype, 'getAnimations', {
  configurable: true,
  value: () => [],
});

beforeEach(async () => {
  document.body.innerHTML = '<div data-app="true"></div>';
  localStorage.clear();
  await initI18n('en-US');
});

afterEach(() => {
  document.body.innerHTML = '';
});

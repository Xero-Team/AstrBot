export const CHAT_SELECTED_CONFIG_STORAGE_KEY = 'chat.selectedConfigId';

export type ChatMessageType = 'FriendMessage' | 'GroupMessage';

export interface WebchatUmoDetails {
  platformId: string;
  messageType: ChatMessageType;
  username: string;
  sessionKey: string;
  umo: string;
}

function getFromLocalStorage(key: string, fallback: string): string {
  try {
    if (typeof localStorage === 'undefined') {
      return fallback;
    }
    const value = localStorage.getItem(key);
    return value === null || value === undefined ? fallback : value;
  } catch {
    return fallback;
  }
}

function setToLocalStorage(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined') {
      return;
    }
    localStorage.setItem(key, value);
  } catch {
    // Ignore storage errors (e.g. private mode / restricted storage).
  }
}

export function getStoredDashboardUsername(): string {
  return getFromLocalStorage('user', '').trim() || 'guest';
}

export function getStoredSelectedChatConfigId(): string {
  return (
    getFromLocalStorage(CHAT_SELECTED_CONFIG_STORAGE_KEY, '').trim() ||
    'default'
  );
}

export function setStoredSelectedChatConfigId(configId: string): void {
  setToLocalStorage(CHAT_SELECTED_CONFIG_STORAGE_KEY, configId);
}

export function buildWebchatUmoDetails(sessionId: string): WebchatUmoDetails {
  const platformId = 'webchat';
  const username = getStoredDashboardUsername();
  const messageType: ChatMessageType = 'FriendMessage';
  const sessionKey = `${platformId}!${username}!${sessionId}`;
  return {
    platformId,
    messageType,
    username,
    sessionKey,
    umo: `${platformId}:${messageType}:${sessionKey}`,
  };
}

function splitUmo(umo: string): [string, string, string] | null {
  const first = umo.indexOf(':');
  if (first < 0) {
    return null;
  }
  const second = umo.indexOf(':', first + 1);
  if (second < 0) {
    return null;
  }
  return [
    umo.slice(0, first),
    umo.slice(first + 1, second),
    umo.slice(second + 1),
  ];
}

function globToRegExp(pattern: string): RegExp {
  let source = '^';
  let index = 0;
  while (index < pattern.length) {
    const char = pattern[index];
    index += 1;
    if (char === '*') {
      source += '.*';
      while (pattern[index] === '*') {
        index += 1;
      }
    } else if (char === '?') {
      source += '.';
    } else if (char === '[') {
      let cursor = index;
      let negate = false;
      if (pattern[cursor] === '!') {
        negate = true;
        cursor += 1;
      }
      const bodyStart = cursor;
      if (pattern[cursor] === ']') {
        cursor += 1;
      }
      while (cursor < pattern.length && pattern[cursor] !== ']') {
        cursor += 1;
      }
      if (cursor >= pattern.length) {
        source += '\\[';
      } else {
        const body = pattern
          .slice(bodyStart, cursor)
          .replace(/([\\^\]])/g, '\\$1');
        source += `[${negate ? '^' : ''}${body}]`;
        index = cursor + 1;
      }
    } else {
      source += char.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
  }
  source += '$';
  return new RegExp(source, 's');
}

function globMatch(value: string, pattern: string): boolean {
  try {
    return globToRegExp(pattern).test(value);
  } catch {
    // Python's fnmatch treats invalid ranges (for example ``[b-a]``) as a
    // never-matching class, while JavaScript's RegExp constructor throws.
    return false;
  }
}

type SegmentPriority = [number, number];
type RoutePriority = [SegmentPriority, SegmentPriority, SegmentPriority];

function segmentPriority(segment: string): SegmentPriority {
  if (segment === '' || segment === '*') {
    return [0, 0];
  }
  if (/[*?[\]]/.test(segment)) {
    return [1, segment.replace(/[*?[\]]/g, '').length];
  }
  return [2, segment.length];
}

function routePriority(pattern: string): RoutePriority {
  const parts = splitUmo(pattern);
  if (!parts) {
    return [
      [-1, -1],
      [-1, -1],
      [-1, -1],
    ];
  }
  return [
    segmentPriority(parts[0]),
    segmentPriority(parts[1]),
    segmentPriority(parts[2]),
  ];
}

function compareRoutePriority(a: RoutePriority, b: RoutePriority): number {
  for (let index = 0; index < 3; index += 1) {
    if (a[index][0] !== b[index][0]) {
      return a[index][0] - b[index][0];
    }
    if (a[index][1] !== b[index][1]) {
      return a[index][1] - b[index][1];
    }
  }
  return 0;
}

function umoPatternMatches(
  pattern: string,
  target: [string, string, string],
): boolean {
  const parts = splitUmo(pattern);
  if (!parts) {
    return false;
  }
  return parts.every(
    (part, index) => part === '' || globMatch(target[index], part),
  );
}

export function resolveConfigIdFromRouting(
  routing: Record<string, string> | null | undefined,
  umo: string | null,
): string {
  const target = umo ? splitUmo(umo) : null;
  if (!target || !routing) {
    return 'default';
  }
  const entries = Object.entries(routing).filter(
    ([pattern, confId]) =>
      typeof confId === 'string' &&
      confId.length > 0 &&
      splitUmo(pattern) !== null,
  );
  entries.sort(([patternA], [patternB]) =>
    compareRoutePriority(routePriority(patternB), routePriority(patternA)),
  );
  for (const [pattern, confId] of entries) {
    if (umoPatternMatches(pattern, target)) {
      return confId;
    }
  }
  return 'default';
}

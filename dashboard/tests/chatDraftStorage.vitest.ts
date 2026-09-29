import { describe, expect, it } from 'vitest';

import {
  CHAT_DRAFT_STORAGE_PREFIX,
  readChatDraft,
  writeChatDraft,
} from '../src/utils/chatDraftStorage';

function createStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => Array.from(map.keys())[index] ?? null,
    removeItem: (key: string) => {
      map.delete(key);
    },
    setItem: (key: string, value: string) => {
      map.set(key, value);
    },
  } as Storage;
}

describe('chat draft storage', () => {
  it('round-trips a session draft', () => {
    const storage = createStorage();
    writeChatDraft('session-1', 'hello', storage);
    expect(storage.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}session-1`)).toBe(
      'hello',
    );
    expect(readChatDraft('session-1', storage)).toBe('hello');
  });

  it('removes the key when the draft is cleared', () => {
    const storage = createStorage();
    writeChatDraft('session-1', 'hello', storage);
    writeChatDraft('session-1', '', storage);
    expect(storage.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}session-1`)).toBeNull();
  });

  it('stores the new-conversation composer under the "new" key', () => {
    const storage = createStorage();
    writeChatDraft('', 'fresh', storage);
    expect(storage.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}new`)).toBe('fresh');
    expect(readChatDraft('', storage)).toBe('fresh');
  });

  it('returns an empty string when no draft is stored', () => {
    expect(readChatDraft('missing', createStorage())).toBe('');
  });

  it('swallows storage failures', () => {
    const throwing = {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      },
      removeItem: () => {
        throw new Error('blocked');
      },
    } as unknown as Storage;
    expect(readChatDraft('session-1', throwing)).toBe('');
    expect(() => writeChatDraft('session-1', 'x', throwing)).not.toThrow();
  });
});

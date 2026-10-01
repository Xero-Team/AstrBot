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
    writeChatDraft('alice', 'session-1', 'hello', storage);
    expect(storage.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}alice.session-1`)).toBe(
      'hello',
    );
    expect(readChatDraft('alice', 'session-1', storage)).toBe('hello');
  });

  it('removes the key when the draft is cleared', () => {
    const storage = createStorage();
    writeChatDraft('alice', 'session-1', 'hello', storage);
    writeChatDraft('alice', 'session-1', '', storage);
    expect(
      storage.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}alice.session-1`),
    ).toBeNull();
  });

  it('isolates the new-conversation composer by dashboard account', () => {
    const storage = createStorage();
    writeChatDraft('alice', '', 'fresh', storage);
    expect(storage.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}alice.new`)).toBe(
      'fresh',
    );
    expect(readChatDraft('alice', '', storage)).toBe('fresh');
    expect(readChatDraft('bob', '', storage)).toBe('');
  });

  it('does not persist drafts without an authenticated owner', () => {
    const storage = createStorage();
    writeChatDraft('', '', 'fresh', storage);
    expect(storage.length).toBe(0);
    expect(readChatDraft('', '', storage)).toBe('');
  });

  it('returns an empty string when no draft is stored', () => {
    expect(readChatDraft('alice', 'missing', createStorage())).toBe('');
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
    expect(readChatDraft('alice', 'session-1', throwing)).toBe('');
    expect(() =>
      writeChatDraft('alice', 'session-1', 'x', throwing),
    ).not.toThrow();
  });
});

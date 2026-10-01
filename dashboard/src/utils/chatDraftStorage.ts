export const CHAT_DRAFT_STORAGE_PREFIX = 'astrbot.chat.draft.';

/** Build an account-scoped draft key, or disable persistence without an owner. */
function draftStorageKey(owner: string, sessionId: string): string | null {
  const normalizedOwner = owner.trim();
  if (!normalizedOwner) return null;
  return `${CHAT_DRAFT_STORAGE_PREFIX}${encodeURIComponent(normalizedOwner)}.${sessionId || 'new'}`;
}

/**
 * Read the text draft for a session or the new-conversation composer.
 *
 * @param owner The authenticated dashboard username.
 * @param sessionId The active session ID, or an empty string for a new conversation.
 * @param storage An optional storage implementation.
 * @returns The stored draft, or an empty string when unavailable.
 */
export function readChatDraft(
  owner: string,
  sessionId: string,
  storage?: Storage,
): string {
  try {
    const target = storage ?? globalThis.localStorage;
    const key = draftStorageKey(owner, sessionId);
    return key ? target?.getItem(key) || '' : '';
  } catch {
    return '';
  }
}

/**
 * Persist or remove the text draft for a session or new conversation.
 *
 * @param owner The authenticated dashboard username.
 * @param sessionId The active session ID, or an empty string for a new conversation.
 * @param draft The draft text to persist.
 * @param storage An optional storage implementation.
 * @returns Nothing.
 */
export function writeChatDraft(
  owner: string,
  sessionId: string,
  draft: string,
  storage?: Storage,
): void {
  try {
    const target = storage ?? globalThis.localStorage;
    const key = draftStorageKey(owner, sessionId);
    if (!key) return;
    if (draft) {
      target?.setItem(key, draft);
    } else {
      target?.removeItem(key);
    }
  } catch {
    // Draft persistence must not block composing or sending a message.
  }
}

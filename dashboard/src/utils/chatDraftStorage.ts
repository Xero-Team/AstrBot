export const CHAT_DRAFT_STORAGE_PREFIX = 'astrbot.chat.draft.';

/**
 * Read the text draft for a session or the new-conversation composer.
 *
 * @param sessionId The active session ID, or an empty string for a new conversation.
 * @param storage An optional storage implementation.
 * @returns The stored draft, or an empty string when unavailable.
 */
export function readChatDraft(sessionId: string, storage?: Storage): string {
  try {
    const target = storage ?? globalThis.localStorage;
    return (
      target?.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}${sessionId || 'new'}`) || ''
    );
  } catch {
    return '';
  }
}

/**
 * Persist or remove the text draft for a session or new conversation.
 *
 * @param sessionId The active session ID, or an empty string for a new conversation.
 * @param draft The draft text to persist.
 * @param storage An optional storage implementation.
 * @returns Nothing.
 */
export function writeChatDraft(
  sessionId: string,
  draft: string,
  storage?: Storage,
): void {
  try {
    const target = storage ?? globalThis.localStorage;
    const key = `${CHAT_DRAFT_STORAGE_PREFIX}${sessionId || 'new'}`;
    if (draft) {
      target?.setItem(key, draft);
    } else {
      target?.removeItem(key);
    }
  } catch {
    // Draft persistence must not block composing or sending a message.
  }
}

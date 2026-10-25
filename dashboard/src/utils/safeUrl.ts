/**
 * Return an absolute http(s) URL, or null for any other scheme or malformed
 * value. Untrusted metadata and tool results must pass through this helper
 * before reaching href, window.open, or iframe-like navigation.
 */
export function safeHttpUrl(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) {
    return null;
  }

  try {
    const parsed = new URL(value.trim());
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

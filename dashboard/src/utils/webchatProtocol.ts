export const WEBCHAT_SUBPROTOCOL = 'astrbot';

/**
 * Build the `Sec-WebSocket-Protocol` list for the unified chat socket.
 *
 * The Dashboard JWT travels as the second protocol so it never appears in the
 * URL. An empty token must not be offered: browsers reject an empty protocol
 * with a SyntaxError before the socket is created.
 */
export function webchatProtocols(token: string): string[] {
  const value = token.trim();
  return value ? [WEBCHAT_SUBPROTOCOL, value] : [WEBCHAT_SUBPROTOCOL];
}

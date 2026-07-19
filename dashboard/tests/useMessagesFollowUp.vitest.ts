import { describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

const testState = vi.hoisted(() => ({
  sockets: [] as MockWebSocket[],
}));

vi.mock('@/api/v1', () => ({
  chatApi: {
    unifiedWebSocketUrl: () => 'ws://example.test/unified-chat',
  },
  fileApi: {},
}));

vi.mock('@/api/http', () => ({
  fetchWithAuth: vi.fn(),
}));

import { useMessages } from '@/composables/useMessages';

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = MockWebSocket.CONNECTING;
  readonly OPEN = MockWebSocket.OPEN;
  readonly CLOSING = MockWebSocket.CLOSING;
  readonly CLOSED = MockWebSocket.CLOSED;
  readyState = MockWebSocket.OPEN;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void | Promise<void>) | null = null;

  constructor(_url: string) {
    testState.sockets.push(this);
  }

  addEventListener(_type: string, _listener: () => void, _options?: unknown) {}

  close() {
    this.readyState = MockWebSocket.CLOSED;
    void this.onclose?.();
  }

  send(_data: string) {}

  emit(payload: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

describe('useMessages follow-up streams', () => {
  it('keeps a captured follow-up with its target run and routes concurrent events', () => {
    vi.stubGlobal('WebSocket', MockWebSocket);
    const sessionId = 'session-1';
    const messages = useMessages({ currentSessionId: ref(sessionId) });
    const first = messages.createLocalExchange({
      sessionId,
      messageId: 'request-1',
      parts: [{ type: 'plain', text: 'first' }],
    });

    messages.sendMessageStream({
      sessionId,
      messageId: 'request-1',
      parts: [{ type: 'plain', text: 'first' }],
      transport: 'websocket',
      botRecord: first.botRecord,
      userRecord: first.userRecord,
    });
    const socket = testState.sockets[0];
    socket.emit({
      ct: 'chat',
      type: 'run_started',
      message_id: 'request-1',
      data: { run_id: 'request-1' },
    });

    const followUp = messages.createLocalExchange({
      sessionId,
      messageId: 'request-2',
      parts: [{ type: 'plain', text: 'follow up' }],
    });
    messages.sendMessageStream({
      sessionId,
      messageId: 'request-2',
      parts: [{ type: 'plain', text: 'follow up' }],
      transport: 'websocket',
      botRecord: followUp.botRecord,
      userRecord: followUp.userRecord,
    });

    socket.emit({
      ct: 'chat',
      type: 'follow_up_captured',
      message_id: 'request-2',
      data: { target_run_id: 'request-1' },
    });
    socket.emit({ ct: 'chat', type: 'end', message_id: 'request-2' });
    socket.emit({
      ct: 'chat',
      type: 'plain',
      message_id: 'request-1',
      data: 'answer',
      streaming: true,
    });

    const records = messages.messagesBySession[sessionId];
    expect(records).toEqual([
      first.userRecord,
      followUp.userRecord,
      first.botRecord,
    ]);
    expect(messages.messageParts(first.botRecord)).toEqual([
      { type: 'plain', text: 'answer' },
    ]);
    expect(messages.isMessageStreaming(first.botRecord, 2)).toBe(true);
    expect(messages.isMessageStreaming(followUp.botRecord, 2)).toBe(false);

    socket.emit({ ct: 'chat', type: 'end', message_id: 'request-1' });
    expect(messages.isSessionRunning(sessionId)).toBe(false);
  });
});

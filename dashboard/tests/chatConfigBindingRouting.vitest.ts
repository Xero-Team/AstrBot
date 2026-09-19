import { describe, expect, it } from 'vitest';
import { resolveConfigIdFromRouting } from '@/utils/chatConfigBinding';

const webchatUmo = 'webchat:FriendMessage:webchat!astrbot!session-1';

describe('resolveConfigIdFromRouting', () => {
  it('matches the backend priority of exact over wildcard over catch-all', () => {
    const routing = {
      '::': 'catch-all',
      'webchat:*:*': 'platform',
      'webchat:FriendMessage:webchat!astrbot!session-1': 'exact',
    };
    expect(resolveConfigIdFromRouting(routing, webchatUmo)).toBe('exact');
    expect(
      resolveConfigIdFromRouting(routing, 'webchat:FriendMessage:other'),
    ).toBe('platform');
    expect(
      resolveConfigIdFromRouting(routing, 'telegram:FriendMessage:other'),
    ).toBe('catch-all');
  });

  it('does not let routing-table insertion order decide the winner', () => {
    const routing = {
      '::': 'catch-all',
      'webchat:*:*': 'platform',
    };
    expect(resolveConfigIdFromRouting(routing, webchatUmo)).toBe('platform');
  });

  it('supports glob patterns in a route segment', () => {
    expect(
      resolveConfigIdFromRouting(
        { 'webchat:FriendMessage:webchat!astrbot!session-[0-9]': 'numbered' },
        webchatUmo,
      ),
    ).toBe('numbered');
    expect(
      resolveConfigIdFromRouting(
        { 'webchat:FriendMessage:webchat!astrbot!session-?': 'single' },
        webchatUmo,
      ),
    ).toBe('single');
    expect(
      resolveConfigIdFromRouting(
        { 'webchat:FriendMessage:webchat!astrbot!session-[0-9]': 'numbered' },
        'webchat:FriendMessage:webchat!astrbot!session-x',
      ),
    ).toBe('default');
  });

  it('matches newlines like the backend DOTALL glob translation', () => {
    expect(
      resolveConfigIdFromRouting(
        { 'webchat:FriendMessage:*': 'catch-all' },
        'webchat:FriendMessage:line\nbreak',
      ),
    ).toBe('catch-all');
    expect(
      resolveConfigIdFromRouting(
        { 'webchat:FriendMessage:line?break': 'question' },
        'webchat:FriendMessage:line\nbreak',
      ),
    ).toBe('question');
  });

  it('preserves colons inside the session segment', () => {
    const routing = {
      'webchat:FriendMessage:webchat!astrbot!session-1:thread': 'thread',
    };
    expect(
      resolveConfigIdFromRouting(
        routing,
        'webchat:FriendMessage:webchat!astrbot!session-1:thread',
      ),
    ).toBe('thread');
  });

  it('falls back to default for malformed input or no match', () => {
    expect(resolveConfigIdFromRouting({ '::': 'catch-all' }, null)).toBe(
      'default',
    );
    expect(resolveConfigIdFromRouting(null, webchatUmo)).toBe('default');
    expect(resolveConfigIdFromRouting({}, webchatUmo)).toBe('default');
    expect(resolveConfigIdFromRouting({ '::': 'catch-all' }, 'invalid')).toBe(
      'default',
    );
  });
});

import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/router', () => ({
  router: { push: vi.fn(), replace: vi.fn(), beforeEach: vi.fn() },
}));
vi.mock('vue-router', async () => {
  const actual =
    await vi.importActual<typeof import('vue-router')>('vue-router');
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  };
});

const api = vi.hoisted(() => ({
  listSessions: vi.fn(),
  upsert: vi.fn(),
  list: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  chatApi: { listSessions: api.listSessions },
  configRouteApi: { upsert: api.upsert, list: api.list },
}));

import { useSessions, type Session } from '@/composables/useSessions';

function session(index: number): Session {
  return {
    session_id: `s${index}`,
    display_name: `Session ${index}`,
    updated_at: '2024-01-01',
    platform_id: 'webchat',
    creator: 'u',
    created_at: '2024-01-01',
  };
}

function page(sessions: Session[], pageNumber: number, total: number) {
  return {
    data: {
      status: 'ok',
      data: {
        sessions,
        page: pageNumber,
        page_size: 30,
        total,
      },
    },
  };
}

describe('sidebar session pagination', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it('loads the newest page and appends older pages', async () => {
    const newest = Array.from({ length: 30 }, (_, index) => session(100 - index));
    const older = Array.from({ length: 5 }, (_, index) => session(70 - index));
    api.listSessions
      .mockResolvedValueOnce(page(newest, 1, 35))
      .mockResolvedValueOnce(page(older, 2, 35));

    const sessions = useSessions();
    await sessions.getSessions();

    expect(sessions.sessions.value.map((item) => item.session_id)).toEqual(
      newest.map((item) => item.session_id),
    );
    expect(sessions.sessionsPagination.page).toBe(1);
    expect(sessions.sessionsPagination.hasMore).toBe(true);

    await sessions.getSessions(true);

    expect(sessions.sessions.value).toHaveLength(35);
    expect(sessions.sessionsPagination.page).toBe(2);
    expect(sessions.sessionsPagination.hasMore).toBe(false);
    expect(api.listSessions).toHaveBeenNthCalledWith(1, {
      page: 1,
      page_size: 30,
    });
    expect(api.listSessions).toHaveBeenNthCalledWith(2, {
      page: 2,
      page_size: 30,
    });
  });

  it('deduplicates sessions across overlapping pages', async () => {
    const newest = Array.from({ length: 30 }, (_, index) => session(30 - index));
    const overlap = [session(3), session(2), session(1)];
    api.listSessions
      .mockResolvedValueOnce(page(newest, 1, 33))
      .mockResolvedValueOnce(page(overlap, 2, 33));

    const sessions = useSessions();
    await sessions.getSessions();
    expect(sessions.sessionsPagination.hasMore).toBe(true);
    await sessions.getSessions(true);

    expect(sessions.sessions.value).toHaveLength(30);
    expect(sessions.sessionsPagination.hasMore).toBe(false);
  });

  it('records a load error without dropping the current list', async () => {
    api.listSessions.mockRejectedValueOnce(new Error('offline'));

    const sessions = useSessions();
    await sessions.getSessions();

    expect(sessions.sessionsPagination.error).toBe(true);
    expect(sessions.sessionsPagination.loading).toBe(false);
    expect(sessions.sessions.value).toEqual([]);
  });

  it('does not request another page when the list is exhausted', async () => {
    api.listSessions.mockResolvedValueOnce(page([session(1)], 1, 1));

    const sessions = useSessions();
    await sessions.getSessions();

    expect(sessions.sessionsPagination.hasMore).toBe(false);
    api.listSessions.mockClear();

    await sessions.getSessions(true);

    expect(api.listSessions).not.toHaveBeenCalled();
  });
});

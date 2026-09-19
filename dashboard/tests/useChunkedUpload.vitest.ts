import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useChunkedUpload } from '@/composables/useChunkedUpload';
import type { ChunkedUploadApi } from '@/composables/useChunkedUpload';

function ok(data: unknown = {}) {
  return Promise.resolve({ data: { status: 'ok' as const, data } });
}

function fail(message: string) {
  return Promise.resolve({
    data: { status: 'error' as const, message, data: {} },
  });
}

function makeFile(size = 10, name = 'notes.bin') {
  return new File(['x'.repeat(size)], name, {
    type: 'application/octet-stream',
  });
}

function mockApi(overrides: Partial<ChunkedUploadApi> = {}): ChunkedUploadApi {
  return {
    initUpload: vi.fn(() =>
      ok({ upload_id: 'u1', chunk_size: 4, total_chunks: 3 }),
    ),
    uploadChunk: vi.fn(() => ok({})),
    completeUpload: vi.fn(() =>
      ok({ attachment_id: 'a1', filename: 'notes.bin', type: 'file' }),
    ),
    abortUpload: vi.fn(() => ok({})),
    statusUpload: vi.fn(() =>
      ok({ received_chunks: [], total_chunks: 3, chunk_size: 4 }),
    ),
    ...overrides,
  };
}

describe('useChunkedUpload', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('reports zero percent before any bytes are planned', () => {
    const uploader = useChunkedUpload(mockApi());
    expect(uploader.percent.value).toBe(0);
    expect(uploader.canResume.value).toBe(false);
  });

  it('uploads every chunk then returns the complete payload', async () => {
    const api = mockApi();
    const uploader = useChunkedUpload(api);
    const result = await uploader.start(makeFile());

    expect(api.initUpload).toHaveBeenCalledWith({
      filename: 'notes.bin',
      total_size: 10,
    });
    expect(api.uploadChunk).toHaveBeenCalledTimes(3);
    expect(result).toEqual({
      attachment_id: 'a1',
      filename: 'notes.bin',
      type: 'file',
    });
    expect(uploader.status.value).toBe('done');
    expect(uploader.percent.value).toBe(100);
  });

  it('retries a failed chunk and then succeeds', async () => {
    const api = mockApi({
      initUpload: vi.fn(() =>
        ok({ upload_id: 'u1', chunk_size: 4, total_chunks: 1 }),
      ),
      uploadChunk: vi
        .fn()
        .mockRejectedValueOnce(new Error('temp'))
        .mockRejectedValueOnce({ response: { data: { message: 'retry' } } })
        .mockImplementation(() => ok({})),
    });
    const uploader = useChunkedUpload(api);
    await uploader.start(makeFile(4));
    expect(api.uploadChunk).toHaveBeenCalledTimes(3);
    expect(uploader.status.value).toBe('done');
  });

  it('surfaces envelope and exhausted chunk errors for resume', async () => {
    const api = mockApi({
      initUpload: vi.fn(() => fail('init denied')),
    });
    const uploader = useChunkedUpload(api);
    expect(await uploader.start(makeFile())).toBeUndefined();
    expect(uploader.status.value).toBe('error');
    expect(uploader.errorMessage.value).toBe('init denied');
    expect(uploader.canResume.value).toBe(true);

    api.initUpload = vi.fn(() =>
      ok({ upload_id: 'u2', chunk_size: 10, total_chunks: 1 }),
    );
    api.uploadChunk = vi.fn().mockRejectedValue(new Error('chunk down'));
    expect(await uploader.resume()).toBeUndefined();
    expect(uploader.errorMessage.value).toBe('chunk down');
  });

  it('reinitializes when status lookup fails and skips received chunks', async () => {
    const api = mockApi({
      statusUpload: vi.fn(() => fail('gone')),
    });
    const uploader = useChunkedUpload(api);
    await uploader.start(makeFile());
    uploader.status.value = 'error';

    api.statusUpload = vi.fn(() => fail('gone'));
    api.initUpload = vi.fn(() =>
      ok({ upload_id: 'u9', chunk_size: 10, total_chunks: 1 }),
    );
    const result = await uploader.resume();
    expect(api.initUpload).toHaveBeenCalled();
    expect(result).toEqual({
      attachment_id: 'a1',
      filename: 'notes.bin',
      type: 'file',
    });
  });

  it('resumes only the missing chunks after a status hit', async () => {
    const api = mockApi();
    const uploader = useChunkedUpload(api);
    expect(await uploader.start(makeFile())).toBeDefined();
    uploader.status.value = 'error';
    api.uploadChunk = vi.fn(() => ok({}));
    api.statusUpload = vi.fn(() => ok({ received_chunks: [0, 1] }));
    await uploader.resume();
    expect(api.uploadChunk).toHaveBeenCalledTimes(1);
    expect(api.uploadChunk).toHaveBeenCalledWith(
      expect.objectContaining({ chunk_index: 2 }),
    );
  });

  it('returns undefined from resume when no file is staged', async () => {
    const uploader = useChunkedUpload(mockApi());
    expect(await uploader.resume()).toBeUndefined();
  });

  it('aborts the session on cancel and logs abort failures', async () => {
    let releaseChunk: ((value: unknown) => void) | undefined;
    const abortError = new Error('abort failed');
    const api = mockApi({
      initUpload: vi.fn(() =>
        ok({ upload_id: 'u1', chunk_size: 10, total_chunks: 1 }),
      ),
      uploadChunk: vi.fn(
        () =>
          new Promise((resolve) => {
            releaseChunk = resolve;
          }),
      ),
      abortUpload: vi.fn(() => Promise.reject(abortError)),
    });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const uploader = useChunkedUpload(api);
    const started = uploader.start(makeFile());
    await vi.waitFor(() => expect(api.uploadChunk).toHaveBeenCalled());
    const cancelled = uploader.cancel();
    releaseChunk?.({ data: { status: 'ok', data: {} } });
    expect(await started).toBeUndefined();
    await cancelled;
    expect(uploader.status.value).toBe('idle');
    expect(api.abortUpload).toHaveBeenCalledWith({ upload_id: 'u1' });
    expect(errorSpy).toHaveBeenCalledWith(
      'Failed to abort upload:',
      abortError,
    );
  });

  it('ignores a complete payload after cancel and resets', async () => {
    let finishComplete: ((value: unknown) => void) | undefined;
    const api = mockApi({
      completeUpload: vi.fn(
        () =>
          new Promise((resolve) => {
            finishComplete = resolve;
          }),
      ),
    });
    const uploader = useChunkedUpload(api);
    const started = uploader.start(makeFile());
    await vi.waitFor(() => expect(api.completeUpload).toHaveBeenCalled());
    const cancelled = uploader.cancel();
    finishComplete?.({ data: { status: 'ok', data: { filename: 'late' } } });
    expect(await started).toBeUndefined();
    await cancelled;
    expect(uploader.status.value).toBe('idle');
  });

  it('clears the session id after a failed complete so resume re-inits', async () => {
    const api = mockApi({
      completeUpload: vi.fn(() => fail('merge failed')),
    });
    const uploader = useChunkedUpload(api);
    await uploader.start(makeFile());
    expect(uploader.phase.value).toBe('complete');
    api.initUpload = vi.fn(() =>
      ok({ upload_id: 'fresh', chunk_size: 10, total_chunks: 1 }),
    );
    api.completeUpload = vi.fn(() => ok({ filename: 'ok.bin' }));
    const result = await uploader.resume();
    expect(api.initUpload).toHaveBeenCalled();
    expect(result).toEqual({ filename: 'ok.bin' });
  });

  it('rejects malformed init payloads', async () => {
    const api = mockApi({
      initUpload: vi.fn(() => ok({ upload_id: 1 })),
    });
    const uploader = useChunkedUpload(api);
    expect(await uploader.start(makeFile())).toBeUndefined();
    expect(uploader.errorMessage.value).toBe('Upload failed');
  });
});

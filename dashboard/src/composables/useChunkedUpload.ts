import { ref, computed } from 'vue';
import { resolveErrorMessage } from '@/utils/errorUtils';

export interface ChunkedUploadEnvelope<T = unknown> {
  data?: {
    status?: string;
    message?: string | null;
    data?: T;
  };
}

export interface ChunkedUploadApi {
  initUpload(payload: {
    filename: string;
    total_size: number;
  }): Promise<ChunkedUploadEnvelope>;
  uploadChunk(payload: {
    upload_id: string;
    chunk_index: number;
    chunk: Blob;
  }): Promise<ChunkedUploadEnvelope>;
  completeUpload(payload: {
    upload_id: string;
  }): Promise<ChunkedUploadEnvelope>;
  abortUpload(payload: { upload_id: string }): Promise<ChunkedUploadEnvelope>;
  statusUpload(payload: { upload_id: string }): Promise<ChunkedUploadEnvelope>;
}

export type ChunkedUploadStatus = 'idle' | 'uploading' | 'error' | 'done';
export type ChunkedUploadPhase = 'init' | 'chunks' | 'complete';

interface ChunkedUploadInitData {
  upload_id: string;
  chunk_size: number;
  total_chunks: number;
}

const CONCURRENT_UPLOADS = 5;
const CHUNK_MAX_ATTEMPTS = 3;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function envelopeData(response: ChunkedUploadEnvelope): unknown {
  if (response.data?.status !== 'ok') {
    throw new Error(response.data?.message || 'Upload failed');
  }
  return response.data.data;
}

function asInitData(data: unknown): ChunkedUploadInitData {
  if (!isRecord(data)) {
    throw new Error('Upload failed');
  }
  const {
    upload_id: uploadId,
    chunk_size: chunkSize,
    total_chunks: totalChunks,
  } = data;
  if (
    typeof uploadId !== 'string' ||
    typeof chunkSize !== 'number' ||
    typeof totalChunks !== 'number'
  ) {
    throw new Error('Upload failed');
  }
  return {
    upload_id: uploadId,
    chunk_size: chunkSize,
    total_chunks: totalChunks,
  };
}

function asReceivedChunks(data: unknown): number[] {
  if (!isRecord(data) || !Array.isArray(data.received_chunks)) {
    return [];
  }
  return data.received_chunks.filter(
    (index): index is number => typeof index === 'number',
  );
}

function toError(err: unknown): Error {
  return err instanceof Error
    ? err
    : new Error(resolveErrorMessage(err, 'Upload failed'));
}

export function useChunkedUpload(api: ChunkedUploadApi) {
  const status = ref<ChunkedUploadStatus>('idle');
  const phase = ref<ChunkedUploadPhase>('init');
  const uploadedBytes = ref(0);
  const totalBytes = ref(0);
  const errorMessage = ref('');

  const percent = computed(() =>
    totalBytes.value > 0
      ? Math.round((uploadedBytes.value / totalBytes.value) * 100)
      : 0,
  );
  const canResume = computed(() => status.value === 'error');

  let file: File | null = null;
  let uploadId = '';
  let chunkSize = 0;
  let totalChunks = 0;
  let chunkSizes: number[] = [];
  let cancelled = false;
  let runGeneration = 0;

  function planChunks() {
    if (!file) {
      throw new Error('Upload failed');
    }
    chunkSizes = [];
    for (let i = 0; i < totalChunks; i++) {
      const start = i * chunkSize;
      chunkSizes[i] = Math.min(start + chunkSize, file.size) - start;
    }
  }

  async function uploadOneChunk(
    chunkIndex: number,
    sessionId: string,
    generation: number,
  ) {
    if (!file) {
      throw new Error('Upload failed');
    }
    const start = chunkIndex * chunkSize;
    const chunk = file.slice(start, start + chunkSize);
    let lastError: unknown;
    for (let attempt = 0; attempt < CHUNK_MAX_ATTEMPTS; attempt++) {
      if (cancelled) throw new Error('cancelled');
      try {
        envelopeData(
          await api.uploadChunk({
            upload_id: sessionId,
            chunk_index: chunkIndex,
            chunk,
          }),
        );
        if (generation === runGeneration) {
          uploadedBytes.value += chunkSizes[chunkIndex] ?? 0;
        }
        return;
      } catch (err) {
        lastError = err;
      }
    }
    throw toError(lastError);
  }

  async function runPool(
    indexes: number[],
    sessionId: string,
    generation: number,
  ) {
    const pending = [...indexes];
    const active: Promise<void>[] = [];
    let failure: unknown = null;
    while (
      !failure &&
      !cancelled &&
      (pending.length > 0 || active.length > 0)
    ) {
      while (pending.length > 0 && active.length < CONCURRENT_UPLOADS) {
        const chunkIndex = pending.shift();
        if (chunkIndex === undefined) break;
        const promise = uploadOneChunk(
          chunkIndex,
          sessionId,
          generation,
        ).finally(() => {
          const idx = active.indexOf(promise);
          if (idx > -1) {
            void active.splice(idx, 1);
          }
        });
        active.push(promise);
      }
      if (active.length > 0) {
        try {
          await Promise.race(active);
        } catch (err) {
          failure = err;
        }
      }
    }
    if (active.length > 0) await Promise.allSettled(active);
    if (cancelled) throw new Error('cancelled');
    if (failure) throw toError(failure);
  }

  async function initSession() {
    if (!file) {
      throw new Error('Upload failed');
    }
    phase.value = 'init';
    const data = asInitData(
      envelopeData(
        await api.initUpload({ filename: file.name, total_size: file.size }),
      ),
    );
    uploadId = data.upload_id;
    chunkSize = data.chunk_size;
    totalChunks = data.total_chunks;
    planChunks();
    uploadedBytes.value = 0;
  }

  async function completeSession() {
    phase.value = 'complete';
    const result = envelopeData(
      await api.completeUpload({ upload_id: uploadId }),
    );
    if (cancelled) throw new Error('cancelled');
    return result;
  }

  function handleFailure(err: unknown): undefined {
    if (cancelled || (err instanceof Error && err.message === 'cancelled')) {
      const id = uploadId;
      reset();
      if (id) {
        void api.abortUpload({ upload_id: id }).catch((abortErr: unknown) => {
          console.error('Failed to abort upload:', abortErr);
        });
      }
      return undefined;
    }
    if (phase.value === 'complete') uploadId = '';
    status.value = 'error';
    errorMessage.value = resolveErrorMessage(err, 'Upload failed');
    return undefined;
  }

  async function start(f: File): Promise<unknown> {
    file = f;
    cancelled = false;
    status.value = 'uploading';
    errorMessage.value = '';
    totalBytes.value = f.size;
    try {
      await initSession();
      phase.value = 'chunks';
      await runPool(
        Array.from({ length: totalChunks }, (_, i) => i),
        uploadId,
        ++runGeneration,
      );
      const result = await completeSession();
      status.value = 'done';
      return result;
    } catch (err) {
      handleFailure(err);
      return undefined;
    }
  }

  async function resume(): Promise<unknown> {
    if (!file) return undefined;
    cancelled = false;
    status.value = 'uploading';
    errorMessage.value = '';
    try {
      let received: number[] = [];
      if (uploadId) {
        try {
          received = asReceivedChunks(
            envelopeData(await api.statusUpload({ upload_id: uploadId })),
          );
        } catch {
          uploadId = '';
        }
      }
      if (!uploadId) {
        await initSession();
      } else {
        uploadedBytes.value = received.reduce(
          (sum, i) => sum + (chunkSizes[i] ?? 0),
          0,
        );
      }
      phase.value = 'chunks';
      const missing = Array.from({ length: totalChunks }, (_, i) => i).filter(
        (i) => !received.includes(i),
      );
      await runPool(missing, uploadId, ++runGeneration);
      const result = await completeSession();
      status.value = 'done';
      return result;
    } catch (err) {
      handleFailure(err);
      return undefined;
    }
  }

  async function cancel() {
    cancelled = true;
    runGeneration++;
    const id = uploadId;
    reset();
    if (id) {
      try {
        await api.abortUpload({ upload_id: id });
      } catch (err) {
        console.error('Failed to abort upload:', err);
      }
    }
  }

  function reset() {
    status.value = 'idle';
    phase.value = 'init';
    uploadedBytes.value = 0;
    totalBytes.value = 0;
    errorMessage.value = '';
    file = null;
    uploadId = '';
    chunkSize = 0;
    totalChunks = 0;
    chunkSizes = [];
  }

  return {
    status,
    phase,
    percent,
    uploadedBytes,
    totalBytes,
    errorMessage,
    canResume,
    start,
    resume,
    cancel,
    reset,
  };
}

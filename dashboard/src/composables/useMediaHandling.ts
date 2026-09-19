import { computed, ref, shallowRef } from 'vue';
import { fileApi } from '@/api/v1';
import type { UploadedFileData } from '@/api/v1/types';
import { useChunkedUpload } from '@/composables/useChunkedUpload';

const CHUNKED_UPLOAD_THRESHOLD = 32 * 1024 * 1024;

export interface StagedFileInfo {
  attachment_id: string;
  filename: string;
  original_name: string;
  url: string;
  type: string;
  signature?: string;
}

export interface FailedUploadView {
  name: string;
  size: number;
  error: string;
}

export interface ActiveUploadView {
  name: string;
  size: number;
  percent: number;
}

interface UploadEntry {
  file: File;
  signature: string;
  uploader: ReturnType<typeof useChunkedUpload>;
}

export function useMediaHandling() {
  const stagedFiles = ref<StagedFileInfo[]>([]);
  const mediaCache = ref<Record<string, string>>({});
  const pendingFileSignatures = new Set<string>();
  const failedUploads = shallowRef<UploadEntry[]>([]);
  const activeUploads = shallowRef<UploadEntry[]>([]);

  const failedUploadViews = computed<FailedUploadView[]>(() =>
    failedUploads.value.map((entry) => ({
      name: entry.file.name,
      size: entry.file.size,
      error: entry.uploader.errorMessage.value,
    })),
  );

  const activeUploadViews = computed<ActiveUploadView[]>(() =>
    activeUploads.value.map((entry) => ({
      name: entry.file.name,
      size: entry.file.size,
      percent: entry.uploader.percent.value,
    })),
  );

  async function getFileSignature(file: File): Promise<string> {
    if (crypto?.subtle) {
      const BLOCK = 8 * 1024 * 1024;
      const blockHashes: Uint8Array[] = [];
      for (let offset = 0; offset < file.size; offset += BLOCK) {
        const buf = await file.slice(offset, offset + BLOCK).arrayBuffer();
        blockHashes.push(
          new Uint8Array(await crypto.subtle.digest('SHA-256', buf)),
        );
      }
      const combined = new Uint8Array(blockHashes.length * 32);
      blockHashes.forEach((h, i) => {
        combined.set(h, i * 32);
      });
      const digest = await crypto.subtle.digest('SHA-256', combined);
      const hash = Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, '0'))
        .join('');
      return `sha256m:${hash}`;
    }

    return `meta:${file.name}:${file.size}:${file.type}:${file.lastModified}`;
  }

  function isDuplicateFile(signature: string) {
    return (
      pendingFileSignatures.has(signature) ||
      stagedFiles.value.some((file) => file.signature === signature) ||
      failedUploads.value.some((entry) => entry.signature === signature)
    );
  }

  async function getMediaFile(filename: string): Promise<string> {
    if (mediaCache.value[filename]) {
      return mediaCache.value[filename];
    }

    try {
      const response = await fileApi.getByName(filename);

      const blobUrl = URL.createObjectURL(response.data);
      mediaCache.value[filename] = blobUrl;
      return blobUrl;
    } catch (error) {
      console.error('Error fetching media file:', error);
      return '';
    }
  }

  function asUploadedFileData(data: unknown): UploadedFileData | undefined {
    if (!data || typeof data !== 'object') return undefined;
    const record = data as Record<string, unknown>;
    if (
      typeof record.attachment_id !== 'string' ||
      typeof record.filename !== 'string' ||
      typeof record.type !== 'string'
    ) {
      return undefined;
    }
    return {
      attachment_id: record.attachment_id,
      filename: record.filename,
      type: record.type,
    };
  }

  function stageUploaded(
    file: File,
    data: UploadedFileData,
    signature: string,
  ): StagedFileInfo {
    const stagedFile = {
      attachment_id: data.attachment_id,
      filename: data.filename,
      original_name: file.name,
      url: URL.createObjectURL(file),
      type: data.type,
      signature,
    };
    stagedFiles.value.push(stagedFile);
    return stagedFile;
  }

  async function uploadStagedFile(
    file: File,
  ): Promise<StagedFileInfo | undefined> {
    const signature = await getFileSignature(file);
    if (isDuplicateFile(signature)) return undefined;

    pendingFileSignatures.add(signature);
    try {
      if (file.size >= CHUNKED_UPLOAD_THRESHOLD) {
        return await uploadChunkedStagedFile(file, signature);
      }
      const formData = new FormData();
      formData.append('file', file);
      const response = await fileApi.upload(formData);
      return stageUploaded(file, response.data.data, signature);
    } catch (err) {
      console.error('Error uploading file:', err);
      return undefined;
    } finally {
      pendingFileSignatures.delete(signature);
    }
  }

  async function uploadChunkedStagedFile(
    file: File,
    signature: string,
  ): Promise<StagedFileInfo | undefined> {
    const uploader = useChunkedUpload({
      initUpload: ({ filename, total_size }) =>
        fileApi.initUpload({
          filename,
          total_size,
          content_type: file.type,
        }),
      uploadChunk: fileApi.uploadChunk,
      completeUpload: fileApi.completeUpload,
      abortUpload: fileApi.abortUpload,
      statusUpload: fileApi.statusUpload,
    });
    const entry: UploadEntry = { file, signature, uploader };
    activeUploads.value = [...activeUploads.value, entry];
    const result = await uploader.start(file);
    activeUploads.value = activeUploads.value.filter((e) => e !== entry);
    const payload = asUploadedFileData(result);
    if (payload) {
      return stageUploaded(file, payload, signature);
    }
    if (uploader.status.value === 'error') {
      failedUploads.value = [...failedUploads.value, entry];
    }
    return undefined;
  }

  function cancelActiveUpload(index: number) {
    const entry = activeUploads.value[index];
    if (!entry) return;
    void entry.uploader.cancel();
  }

  async function retryFailedUpload(
    index: number,
  ): Promise<StagedFileInfo | undefined> {
    const entry = failedUploads.value[index];
    if (!entry) return undefined;
    failedUploads.value = failedUploads.value.filter((e) => e !== entry);
    activeUploads.value = [...activeUploads.value, entry];
    const result = await entry.uploader.resume();
    activeUploads.value = activeUploads.value.filter((e) => e !== entry);
    if (!result) {
      if (entry.uploader.status.value === 'error') {
        failedUploads.value = [...failedUploads.value, entry];
      }
      return undefined;
    }
    const payload = asUploadedFileData(result);
    if (!payload) return undefined;
    return stageUploaded(entry.file, payload, entry.signature);
  }

  async function discardFailedUpload(index: number) {
    const entry = failedUploads.value[index];
    if (!entry) return;
    failedUploads.value = failedUploads.value.filter((e) => e !== entry);
    await entry.uploader.cancel();
  }

  async function processAndUploadImage(file: File) {
    return uploadStagedFile(file);
  }

  async function processAndUploadFile(file: File) {
    return uploadStagedFile(file);
  }

  async function handlePaste(event: ClipboardEvent) {
    const items = event.clipboardData?.items;
    if (!items) return;

    for (let i = 0; i < items.length; i++) {
      if (items[i].type.includes('image')) {
        const file = items[i].getAsFile();
        if (file) {
          await processAndUploadImage(file);
        }
      }
    }
  }

  function removeImage(index: number) {
    let imageCount = 0;
    for (let i = 0; i < stagedFiles.value.length; i++) {
      if (stagedFiles.value[i].type === 'image') {
        if (imageCount === index) {
          const fileToRemove = stagedFiles.value[i];
          if (fileToRemove.url.startsWith('blob:')) {
            URL.revokeObjectURL(fileToRemove.url);
          }
          stagedFiles.value.splice(i, 1);
          return;
        }
        imageCount++;
      }
    }
  }

  function removeAudio() {
    for (let i = stagedFiles.value.length - 1; i >= 0; i--) {
      if (stagedFiles.value[i].type !== 'record') continue;

      const fileToRemove = stagedFiles.value[i];
      if (fileToRemove.url.startsWith('blob:')) {
        URL.revokeObjectURL(fileToRemove.url);
      }
      stagedFiles.value.splice(i, 1);
    }
  }

  function removeFile(index: number) {
    let fileCount = 0;
    for (let i = 0; i < stagedFiles.value.length; i++) {
      if (
        stagedFiles.value[i].type !== 'image' &&
        stagedFiles.value[i].type !== 'record'
      ) {
        if (fileCount === index) {
          const fileToRemove = stagedFiles.value[i];
          if (fileToRemove.url.startsWith('blob:')) {
            URL.revokeObjectURL(fileToRemove.url);
          }
          stagedFiles.value.splice(i, 1);
          return;
        }
        fileCount++;
      }
    }
  }

  function clearStaged(options: { revokeUrls?: boolean } = {}) {
    const { revokeUrls = true } = options;
    if (revokeUrls) {
      stagedFiles.value.forEach((file) => {
        if (file.url.startsWith('blob:')) {
          URL.revokeObjectURL(file.url);
        }
      });
    }
    stagedFiles.value = [];
  }

  function cleanupMediaCache() {
    Object.values(mediaCache.value).forEach((url) => {
      if (url.startsWith('blob:')) {
        URL.revokeObjectURL(url);
      }
    });
    mediaCache.value = {};
  }

  const stagedImagesUrl = computed(() =>
    stagedFiles.value.filter((f) => f.type === 'image').map((f) => f.url),
  );

  const stagedAudioUrl = computed(
    () => stagedFiles.value.find((f) => f.type === 'record')?.url || '',
  );

  const stagedNonImageFiles = computed(() =>
    stagedFiles.value.filter((f) => f.type !== 'image' && f.type !== 'record'),
  );

  return {
    stagedImagesUrl,
    stagedAudioUrl,
    stagedFiles,
    stagedNonImageFiles,
    failedUploadViews,
    activeUploadViews,
    getMediaFile,
    processAndUploadImage,
    processAndUploadFile,
    handlePaste,
    removeImage,
    removeAudio,
    removeFile,
    retryFailedUpload,
    discardFailedUpload,
    cancelActiveUpload,
    clearStaged,
    cleanupMediaCache,
  };
}

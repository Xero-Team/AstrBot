import { generatedFormData, openApiV1, typed } from './shared';
import type {
  AxiosResponse,
  ChatChunkUploadRequest,
  FileUploadRequest,
} from './shared';
import type { OpenConfig, UploadedFileData } from './types';

export const fileApi = {
  upload(formData: FormData) {
    return typed<UploadedFileData>(
      openApiV1.uploadFile({
        body: generatedFormData(formData) as unknown as FileUploadRequest,
      }),
    );
  },
  initUpload(payload: {
    filename: string;
    total_size: number;
    content_type?: string;
  }) {
    return typed<OpenConfig>(openApiV1.initFileUpload({ body: payload }));
  },
  uploadChunk(payload: {
    upload_id: string;
    chunk_index: number;
    chunk: Blob;
  }) {
    const formData = new FormData();
    formData.append('upload_id', payload.upload_id);
    formData.append('chunk_index', String(payload.chunk_index));
    formData.append('chunk', payload.chunk);
    return typed<OpenConfig>(
      openApiV1.uploadFileChunk({
        body: generatedFormData(formData) as unknown as ChatChunkUploadRequest,
      }),
    );
  },
  completeUpload(payload: { upload_id: string }) {
    return typed<OpenConfig>(openApiV1.completeFileUpload({ body: payload }));
  },
  abortUpload(payload: { upload_id: string }) {
    return typed<OpenConfig>(openApiV1.abortFileUpload({ body: payload }));
  },
  statusUpload(payload: { upload_id: string }) {
    return typed<OpenConfig>(openApiV1.statusFileUpload({ body: payload }));
  },
  getByName(filename: string) {
    return openApiV1.getFileByName({
      query: { filename },
      responseType: 'blob',
    }) as Promise<AxiosResponse<Blob>>;
  },
  byNameUrl(filename: string) {
    return `/api/v1/files/content?filename=${encodeURIComponent(filename)}`;
  },
  contentUrl(attachmentId: string) {
    return `/api/v1/files/${encodeURIComponent(attachmentId)}/content`;
  },
  tokenUrl(fileToken: string) {
    return `/api/v1/files/tokens/${encodeURIComponent(fileToken)}`;
  },
};

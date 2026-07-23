import { generatedFormData, openApiV1, typed } from './shared';
import type { AxiosResponse, FileUploadRequest } from './shared';
import type { UploadedFileData } from './types';

export const fileApi = {
  upload(formData: FormData) {
    return typed<UploadedFileData>(
      openApiV1.uploadFile({
        body: generatedFormData(formData) as unknown as FileUploadRequest,
      }),
    );
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

import { generatedFormData, openApiV1, typed } from './shared';
import type {
  KnowledgeBaseCreateRequest,
  KnowledgeBaseRequest,
  KnowledgeDocumentUploadRequest,
  KnowledgeDocumentUrlImportRequest,
} from './shared';
import type {
  KnowledgeBaseData,
  KnowledgeChunkData,
  KnowledgeDocumentData,
  KnowledgeRetrieveData,
  OpenConfig,
  PagedItemsData,
} from './types';

export const knowledgeApi = {
  list(params?: {
    page?: number;
    page_size?: number;
    refresh_stats?: boolean;
  }) {
    return typed<PagedItemsData<KnowledgeBaseData>>(
      openApiV1.listKnowledgeBases({ query: params }),
    );
  },
  get(kbId: string) {
    return typed<KnowledgeBaseData>(
      openApiV1.getKnowledgeBase({ path: { kb_id: kbId } }),
    );
  },
  create(config: KnowledgeBaseCreateRequest) {
    return typed<OpenConfig>(openApiV1.createKnowledgeBase({ body: config }));
  },
  update(kbId: string, config: KnowledgeBaseRequest) {
    return typed<OpenConfig>(
      openApiV1.updateKnowledgeBase({
        path: { kb_id: kbId },
        body: config,
      }),
    );
  },
  delete(kbId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteKnowledgeBase({ path: { kb_id: kbId } }),
    );
  },
  documents(
    kbId: string,
    params?: { page?: number; page_size?: number; search?: string },
  ) {
    return typed<PagedItemsData<KnowledgeDocumentData>>(
      openApiV1.listKnowledgeDocuments({
        path: { kb_id: kbId },
        query: params,
      }),
    );
  },
  uploadDocument(kbId: string, formData: FormData) {
    return typed<OpenConfig>(
      openApiV1.uploadKnowledgeDocument({
        path: { kb_id: kbId },
        body: generatedFormData(
          formData,
        ) as unknown as KnowledgeDocumentUploadRequest,
      }),
    );
  },
  importDocumentFromUrl(
    kbId: string,
    payload: KnowledgeDocumentUrlImportRequest,
  ) {
    return typed<OpenConfig>(
      openApiV1.importKnowledgeDocumentFromUrl({
        path: { kb_id: kbId },
        body: payload,
      }),
    );
  },
  task(taskId: string) {
    return typed<OpenConfig>(
      openApiV1.getKnowledgeTask({ path: { task_id: taskId } }),
    );
  },
  document(kbId: string, documentId: string) {
    return typed<KnowledgeDocumentData>(
      openApiV1.getKnowledgeDocument({
        path: { kb_id: kbId, document_id: documentId },
      }),
    );
  },
  deleteDocument(kbId: string, documentId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteKnowledgeDocument({
        path: { kb_id: kbId, document_id: documentId },
      }),
    );
  },
  chunks(
    kbId: string,
    params?: { document_id?: string; page?: number; page_size?: number },
  ) {
    return typed<PagedItemsData<KnowledgeChunkData>>(
      openApiV1.listKnowledgeChunks({
        path: { kb_id: kbId },
        query: params,
      }),
    );
  },
  deleteChunk(kbId: string, chunkId: string, documentId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteKnowledgeChunk({
        path: { kb_id: kbId, chunk_id: chunkId },
        query: { document_id: documentId },
      }),
    );
  },
  retrieve(kbId: string, payload: OpenConfig) {
    return typed<KnowledgeRetrieveData>(
      openApiV1.retrieveKnowledgeBase({
        path: { kb_id: kbId },
        body: payload as never,
      }),
    );
  },
};

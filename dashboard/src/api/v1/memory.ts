import { generatedQuery, openApiV1, typed } from './shared';
import type {
  MemoryFactActionRequest,
  MemoryFactCreateRequest,
  MemoryFactPatchRequest,
  MemoryProfileRefreshRequest,
} from './shared';
import type {
  MemoryFactData,
  MemoryFactDetailData,
  MemoryOperationData,
  MemoryProfileData,
  MemoryStatsData,
  OpenConfig,
  PagedItemsData,
} from './types';

export const memoryApi = {
  facts(params?: {
    page?: number;
    page_size?: number;
    person_id?: string;
    chat_id?: string;
    scope_id?: string;
    status?: 'active' | 'deleted' | 'all';
    query?: string;
  }) {
    return typed<PagedItemsData<MemoryFactData>>(
      openApiV1.listMemoryFacts({ query: generatedQuery(params) }),
    );
  },
  fact(factId: number) {
    return typed<MemoryFactDetailData>(
      openApiV1.getMemoryFact({ path: { fact_id: factId } }),
    );
  },
  createFact(payload: MemoryFactCreateRequest) {
    return typed<MemoryFactData>(openApiV1.createMemoryFact({ body: payload }));
  },
  updateFact(factId: number, payload: MemoryFactPatchRequest) {
    return typed<MemoryFactData>(
      openApiV1.updateMemoryFact({
        path: { fact_id: factId },
        body: payload,
      }),
    );
  },
  deleteFact(factId: number, payload?: MemoryFactActionRequest) {
    return typed<OpenConfig>(
      openApiV1.deleteMemoryFact({
        path: { fact_id: factId },
        body: payload,
      }),
    );
  },
  restoreFact(factId: number, payload?: MemoryFactActionRequest) {
    return typed<OpenConfig>(
      openApiV1.restoreMemoryFact({
        path: { fact_id: factId },
        body: payload,
      }),
    );
  },
  profiles(params?: {
    page?: number;
    page_size?: number;
    person_id?: string;
    chat_scope?: string;
  }) {
    return typed<PagedItemsData<MemoryProfileData>>(
      openApiV1.listMemoryProfiles({ query: generatedQuery(params) }),
    );
  },
  refreshProfile(personId: string, payload: MemoryProfileRefreshRequest) {
    return typed<OpenConfig>(
      openApiV1.refreshMemoryProfile({
        path: { person_id: personId },
        body: payload,
      }),
    );
  },
  operations(params?: {
    page?: number;
    page_size?: number;
    target_type?: string;
    target_id?: string;
  }) {
    return typed<PagedItemsData<MemoryOperationData>>(
      openApiV1.listMemoryOperations({ query: generatedQuery(params) }),
    );
  },
  stats() {
    return typed<MemoryStatsData>(openApiV1.getMemoryStats());
  },
};

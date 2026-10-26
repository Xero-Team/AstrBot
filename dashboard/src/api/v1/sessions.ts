import { generatedQuery, openApiV1, typed } from './shared';
import type {
  BatchSessionProviderRequest,
  BatchSessionServiceRequest,
  SessionGroupRequest,
  SessionRuleRequest,
  UmoListRequest,
} from './shared';
import type {
  ActiveUmosData,
  OpenConfig,
  SessionListParams,
  SessionRuleListData,
  SessionRuleListParams,
} from './types';

interface SenderSuggestion {
  umo: string;
  sender_id: string;
  sender_name: string;
  platform: string;
  display_name: string;
}

interface SenderSuggestionData {
  page: number;
  has_more: boolean;
  senders: SenderSuggestion[];
}

export const sessionApi = {
  senders(params?: {
    search?: string;
    limit?: number;
    page?: number;
    sender_ids?: string[];
  }) {
    return typed<SenderSuggestionData>(
      openApiV1.listSessionSenders({ query: params }),
    );
  },
  list(params?: SessionListParams) {
    return typed<OpenConfig>(
      openApiV1.listSessions({ query: generatedQuery(params) }),
    );
  },
  activeUmos(params?: { platform_id?: string }) {
    return typed<ActiveUmosData>(openApiV1.listActiveUmos({ query: params }));
  },
  listRules(params?: SessionRuleListParams) {
    return typed<SessionRuleListData>(
      openApiV1.listSessionRules({ query: generatedQuery(params) }),
    );
  },
  upsertRule(payload: SessionRuleRequest) {
    return typed<OpenConfig>(openApiV1.upsertSessionRule({ body: payload }));
  },
  deleteRules(payload: UmoListRequest) {
    return typed<OpenConfig>(openApiV1.deleteSessionRules({ body: payload }));
  },
  batchUpdateProvider(payload: BatchSessionProviderRequest) {
    return typed<OpenConfig>(
      openApiV1.batchUpdateSessionProvider({ body: payload }),
    );
  },
  batchUpdateService(payload: BatchSessionServiceRequest) {
    return typed<OpenConfig>(
      openApiV1.batchUpdateSessionService({ body: payload }),
    );
  },
  listGroups() {
    return typed<{ groups: OpenConfig[] }>(openApiV1.listSessionGroups());
  },
  createGroup(payload: SessionGroupRequest) {
    return typed<OpenConfig>(openApiV1.createSessionGroup({ body: payload }));
  },
  updateGroup(groupId: string, payload: SessionGroupRequest) {
    return typed<OpenConfig>(
      openApiV1.updateSessionGroup({
        path: { group_id: groupId },
        body: payload,
      }),
    );
  },
  deleteGroup(groupId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteSessionGroup({ path: { group_id: groupId } }),
    );
  },
};

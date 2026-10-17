import { generatedOptions, openApiV1, typed } from './shared';
import type { AxiosRequestConfig } from './shared';
import type {
  BtwDelegation,
  BtwDelegationEvent,
  BtwWorkSession,
  BtwWorkSessionsEnvelope,
} from '../generated/openapi-v1';

export type { BtwDelegation, BtwDelegationEvent, BtwWorkSession };
export type BtwWorkSessionsPayload = BtwWorkSessionsEnvelope['data'];

export const btwApi = {
  listWorkSessions(requestConfig?: AxiosRequestConfig) {
    return typed<BtwWorkSessionsPayload>(
      openApiV1.listBtwWorkSessions(generatedOptions({}, requestConfig)),
    );
  },
};

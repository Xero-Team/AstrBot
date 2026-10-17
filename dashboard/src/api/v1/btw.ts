import { generatedOptions, openApiV1, typed } from './shared';
import type { AxiosRequestConfig } from './shared';

export interface BtwDelegationEvent {
  type: string;
  timestamp: string;
  summary: string;
  tool: string;
  status: string;
}

export interface BtwDelegation {
  run_id: string;
  agent_id: string;
  agent_name: string;
  agent_type: 'claude_code' | 'codex' | 'opencode' | 'custom';
  workspace: string;
  status: 'running' | 'completed' | 'failed' | 'timed_out' | 'cancelled';
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  latest_action: string;
  event_count: number;
  tool_call_count: number;
  exit_code: number | null;
  detail: string;
  usage: Record<string, number>;
  artifacts: string[];
  recent_events: BtwDelegationEvent[];
}

export interface BtwWorkSession {
  id: string;
  config_id: string;
  origin: string;
  request: string;
  task_type: 'conversation' | 'work';
  status:
    | 'pending'
    | 'running'
    | 'completed'
    | 'failed'
    | 'cancelled'
    | 'unconfirmed';
  created_at: string;
  updated_at: string;
  error: string | null;
  artifacts: string[];
  delegations: BtwDelegation[];
}

export interface BtwWorkSessionsPayload {
  sessions: BtwWorkSession[];
}

export const btwApi = {
  listWorkSessions(requestConfig?: AxiosRequestConfig) {
    return typed<BtwWorkSessionsPayload>(
      openApiV1.listBtwWorkSessions(generatedOptions({}, requestConfig)),
    );
  },
};

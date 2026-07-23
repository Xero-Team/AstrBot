/** Shared chat transport and presentation data. */
export interface MessagePart {
  type: string;
  text?: string;
  think?: string;
  message_id?: string | number;
  selected_text?: string;
  embedded_url?: string;
  embedded_file?: { url?: string; filename?: string; attachment_id?: string };
  attachment_id?: string;
  filename?: string;
  stored_filename?: string;
  tool_calls?: ToolCall[];
  [key: string]: unknown;
}

export interface ToolCall {
  id?: string;
  name?: string;
  arguments?: unknown;
  result?: unknown;
  ts?: number;
  finished_ts?: number;
  [key: string]: unknown;
}

export interface TokenUsageStats {
  input_other?: number | string;
  input_cached?: number | string;
  output?: number | string;
  [key: string]: unknown;
}

export interface AgentStats {
  token_usage?: TokenUsageStats;
  [key: string]: unknown;
}

export interface ChatRefItem {
  index?: unknown;
  title?: string;
  url?: string;
  snippet?: string;
  favicon?: string;
  [key: string]: unknown;
}

export interface ChatRefs {
  used?: ChatRefItem[];
  [key: string]: unknown;
}

export interface ChatContent {
  type: 'user' | 'bot' | string;
  message: MessagePart[];
  reasoning?: string;
  isLoading?: boolean;
  agentStats?: AgentStats | null;
  refs?: ChatRefs | null;
}

export interface StreamPayload {
  ct?: string;
  t?: string;
  type?: string;
  chain_type?: string;
  data?: unknown;
  streaming?: boolean;
  [key: string]: unknown;
}

export interface HistoryRecord {
  id?: string | number;
  content?: {
    type?: string;
    message?: unknown;
    reasoning?: string;
    agentStats?: AgentStats | null;
    agent_stats?: AgentStats | null;
    refs?: ChatRefs | null;
  };
  created_at?: string;
  sender_id?: string;
  sender_name?: string;
  llm_checkpoint_id?: string | null;
  [key: string]: unknown;
}

export interface MessageDisplayBlock {
  kind: 'thinking' | 'content';
  parts: MessagePart[];
}

export interface ChatThread {
  thread_id: string;
  parent_session_id: string;
  parent_message_id: number;
  base_checkpoint_id: string;
  selected_text: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChatRecord {
  id?: string | number;
  content: ChatContent;
  created_at?: string;
  sender_id?: string;
  sender_name?: string;
  llm_checkpoint_id?: string | null;
  threads?: ChatThread[];
}

export interface ChatSessionProject {
  project_id: string;
  title: string;
  emoji?: string;
}

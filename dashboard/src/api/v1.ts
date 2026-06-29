import type { AxiosRequestConfig, AxiosResponse } from 'axios';

import * as openApiV1 from './generated/openapi-v1';
import type {
  BackupChunkUploadRequest,
  BackupExportRequest,
  BackupImportRequest,
  BackupRenameRequest,
  BackupUploadInitRequest,
  BackupUploadRequest,
  BackupUploadSessionRequest,
  BotConfigRequest,
  BotRegistrationRequest,
  ChatMessagePatchRequest,
  ChatMessageRegenerateRequest,
  ChatProjectRequest,
  ChatRequest,
  ChatSessionBatchDeleteRequest,
  ChatSessionPatchRequest,
  ChatThreadCreateRequest,
  ChatThreadMessageRequest,
  CommandPatchRequest,
  ConfigRouteUpsertRequest,
  ConfigRoutesReplaceRequest,
  ConversationBatchDeleteRequest,
  ConversationExportRequest,
  ConversationMessagesReplaceRequest,
  ConversationPatchRequest,
  CreateApiKeyRequest,
  CronJobPatchRequest,
  CronJobRequest,
  DynamicConfig,
  EnabledPatch,
  GhproxyTestRequest,
  KnowledgeDocumentUrlImportRequest,
  LoginRequest,
  ListConversationsData,
  McpServerConfig,
  ModelScopeSyncRequest,
  NeoCandidateActionRequest,
  NeoReleaseActionRequest,
  PersonaFolderRequest,
  PersonaMoveRequest,
  PersonaRequest,
  PipInstallRequest,
  PluginConfigFileDeleteRequest,
  PluginBatchUpdateRequest,
  PluginGithubInstallRequest,
  PluginSourceBindRequest,
  PluginSourceRequest,
  PluginUpdateRequest,
  PluginUrlInstallRequest,
  ProviderConfigRequest,
  BatchSessionProviderRequest,
  BatchSessionServiceRequest,
  FileUploadRequest,
  ReorderRequest,
  SetupAuthRequest,
  SessionGroupRequest,
  SessionRuleRequest,
  UmoListRequest,
  T2iTemplateRequest,
  TotpSetupRequest,
  TraceSettingsRequest,
  UpdateAccountRequest,
  UpdateRequest,
  PluginUploadInstallRequest,
  KnowledgeDocumentUploadRequest,
} from './generated/openapi-v1';
import { client as openApiV1Client } from './generated/openapi-v1/client.gen';
import { httpClient } from './http';
import type {
  CommandItem,
  ToolItem,
} from '../components/extension/componentPanel/types';
import type { ChatContent } from '../composables/useMessages';

openApiV1Client.setConfig({
  axios: httpClient,
  baseURL: '',
  throwOnError: true,
});

export interface ApiEnvelope<T> {
  status: 'ok' | 'error';
  message?: string | null;
  data: T;
}

export const UPGRADE_RECOVERY_EVENT = 'astrbot-upgrade-recovery';
export const UPGRADE_RECOVERY_TOKEN_KEY = 'astrbot-upgrade-recovery-token';

export type OpenConfig = DynamicConfig;

export interface ProviderSchemaData {
  config_schema?: OpenConfig;
  providers?: OpenConfig[];
  provider_sources?: OpenConfig[];
}

export interface ProviderSourceModelsData {
  models?: string[];
  model_metadata?: Record<string, unknown>;
}

export interface ProviderTestData {
  id?: string;
  model?: string | null;
  type?: string | null;
  name?: string;
  status?: string;
  error?: string | null;
}

export interface ProviderEmbeddingDimensionData {
  embedding_dimensions?: number;
  [key: string]: unknown;
}

export interface VersionData {
  version?: string;
  dashboard_version?: string;
  change_pwd_hint?: boolean;
  md5_pwd_hint?: boolean;
  password_upgrade_required?: boolean;
  [key: string]: unknown;
}

export interface PublicVersionData {
  webui_version?: string | null;
  astrbot_version?: string | null;
  astrbot_code_version?: string | null;
  [key: string]: unknown;
}

type StartTimeData = {
  start_time?: number | string | null;
};

export interface AuthLoginData {
  username?: string;
  token?: string;
  password_upgrade_required?: boolean;
  md5_pwd_hint?: boolean;
  change_pwd_hint?: boolean;
  [key: string]: unknown;
}

export interface AuthSetupStatusData {
  setup_required?: boolean;
  skip_default_password_auth?: boolean;
  totp_required?: boolean;
  [key: string]: unknown;
}

export interface TotpSetupData {
  secret?: string | null;
  recovery_code?: string | null;
  recovery_code_hash?: string | null;
  [key: string]: unknown;
}

export interface UpdateCheckData {
  has_new_version: boolean;
  dashboard_has_new_version: boolean;
  [key: string]: unknown;
}

export interface UploadedFileData {
  attachment_id: string;
  filename: string;
  type: string;
  [key: string]: unknown;
}

export interface BotRegistrationData {
  status?: string;
  registration_code?: string;
  interval?: number;
  verification_uri_complete?: string;
  qrcode_img_content?: string;
  qrcode?: string;
  task_id?: string;
  bind_key?: string;
  app_id?: string;
  app_secret?: string;
  appid?: string;
  secret?: string;
  domain?: string;
  weixin_oc_token?: string;
  weixin_oc_account_id?: string;
  weixin_oc_base_url?: string;
  client_id?: string;
  client_secret?: string;
  [key: string]: unknown;
}

export interface CommandListData {
  items?: CommandItem[];
  wake_prefix?: string[];
  summary?: {
    disabled?: number;
    conflicts?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface PagedItemsData<T> {
  items?: T[];
  total?: number;
  page?: number;
  page_size?: number;
  [key: string]: unknown;
}

export interface ChatSessionSummary {
  session_id: string;
  display_name: string | null;
  updated_at: string;
  platform_id: string;
  creator: string;
  is_group: number;
  created_at: string;
  [key: string]: unknown;
}

export interface ChatThreadData {
  thread_id: string;
  parent_session_id: string;
  parent_message_id: number;
  base_checkpoint_id: string;
  selected_text: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ChatSessionProjectData {
  project_id: string;
  title: string;
  emoji?: string;
  [key: string]: unknown;
}

export interface ChatSessionDetailData {
  session_id?: string;
  display_name?: string | null;
  platform_id?: string;
  history?: HistoryRecordData[];
  threads?: ChatThreadData[];
  project?: ProjectData | null;
  [key: string]: unknown;
}

export interface ChatMessageMutationData {
  message?: OpenConfig;
  truncated_after_message?: boolean;
  needs_regenerate?: boolean;
  [key: string]: unknown;
}

export interface ChatBatchDeleteData {
  deleted_count?: number;
  failed_count?: number;
  failed_items?: OpenConfig[];
  [key: string]: unknown;
}

export interface SessionRuleListData {
  rules?: OpenConfig[];
  total?: number;
  available_personas?: OpenConfig[];
  available_chat_providers?: OpenConfig[];
  available_stt_providers?: OpenConfig[];
  available_tts_providers?: OpenConfig[];
  available_plugins?: OpenConfig[];
  available_kbs?: OpenConfig[];
  [key: string]: unknown;
}

export interface UmoInfoData {
  umo: string;
  platform?: string;
  message_type?: string;
  session_id?: string;
  auto_name?: string;
  user_alias?: string;
  display_name?: string;
  [key: string]: unknown;
}

export interface ActiveUmosData {
  umos?: string[];
  umo_infos?: UmoInfoData[];
  [key: string]: unknown;
}

export interface SkillItemData {
  name?: string;
  description?: string;
  path?: string;
  active?: boolean;
  source_type?: string;
  [key: string]: unknown;
}

export type SkillListData =
  | SkillItemData[]
  | {
      skills?: SkillItemData[];
      runtime?: string;
      sandbox_cache?: OpenConfig;
      [key: string]: unknown;
    };

export interface PersonaFolderData {
  folder_id: string;
  name: string;
  parent_id: string | null;
  description: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
  children: PersonaFolderData[];
  [key: string]: unknown;
}

export interface PersonaData {
  persona_id: string;
  system_prompt: string;
  custom_error_message: string | null;
  begin_dialogs: string[];
  tools: string[] | null;
  skills: string[] | null;
  folder_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
}

export interface PersonaFolderMutationData {
  folder?: PersonaFolderData;
  [key: string]: unknown;
}

export interface PersonaFolderInput {
  name?: string;
  parent_id?: string | null;
  description?: string | null;
  [key: string]: unknown;
}

export interface PersonaInput {
  persona_id: string;
  system_prompt: string;
  begin_dialogs?: string[];
  tools?: string[] | null;
  skills?: string[] | null;
  folder_id?: string | null;
  custom_error_message?: string | null;
  [key: string]: unknown;
}

export interface ConversationPaginationData {
  page?: number;
  page_size?: number;
  total?: number;
  total_pages?: number;
  [key: string]: unknown;
}

export interface ConversationRecordData {
  cid?: string;
  user_id?: string;
  title?: string;
  history?: string;
  [key: string]: unknown;
}

export interface ConversationListResponseData {
  conversations?: ConversationRecordData[];
  pagination?: ConversationPaginationData;
  [key: string]: unknown;
}

export interface ConversationBatchDeleteData {
  deleted_count?: number;
  failed_count?: number;
  [key: string]: unknown;
}

export interface KnowledgeBaseData {
  kb_id: string;
  kb_name: string;
  description?: string | null;
  emoji?: string | null;
  init_error?: string | null;
  doc_count?: number;
  chunk_count?: number;
  embedding_provider_id?: string | null;
  rerank_provider_id?: string | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface KnowledgeDocumentData {
  document_id?: string;
  doc_id?: string;
  doc_name: string;
  file_type?: string;
  file_size?: number;
  chunk_count?: number;
  created_at?: string;
  [key: string]: unknown;
}

export interface KnowledgeChunkData {
  chunk_id: string;
  chunk_index: number;
  content: string;
  char_count: number;
  [key: string]: unknown;
}

export interface KnowledgeRetrieveResultData {
  chunk_id: string;
  chunk_index: number;
  doc_name: string;
  char_count: number;
  score: number;
  content: string;
  [key: string]: unknown;
}

export interface KnowledgeRetrieveData {
  results?: KnowledgeRetrieveResultData[];
  visualization?: string | null;
  [key: string]: unknown;
}

export interface PluginData {
  name?: string;
  activated?: boolean;
  reserved?: boolean;
  origin?: string;
  origin_name?: string;
  readme?: string;
  readme_content?: string;
  content?: string;
  [key: string]: unknown;
}

export interface ProjectData {
  project_id: string;
  title: string;
  emoji?: string;
  description?: string;
  created_at: string;
  updated_at: string;
  [key: string]: unknown;
}

export interface DownloadStageData {
  status: 'pending' | 'running' | 'done' | 'error';
  downloaded: number;
  total: number;
  percent: number;
  speed: number;
  [key: string]: unknown;
}

export interface UpdateProgressData {
  id: string;
  status: 'idle' | 'running' | 'success' | 'error';
  stage: string;
  version: string;
  message: string;
  overall_percent: number;
  stages: Record<string, DownloadStageData>;
  [key: string]: unknown;
}

export interface PluginConfigFilesData {
  files?: string[];
  [key: string]: unknown;
}

export interface PluginConfigUploadData {
  uploaded?: string[];
  errors?: OpenConfig[];
  [key: string]: unknown;
}

export interface ReleaseItemData {
  tag_name: string;
  published_at: string;
  body: string;
  [key: string]: unknown;
}

export interface HistoryRecordData {
  content?: ChatContent & {
    agent_stats?: unknown;
  };
  sender_id?: string;
  [key: string]: unknown;
}

export interface ChatThreadDetailData extends ChatThreadData {
  history?: HistoryRecordData[];
}

export interface BaseStatsData {
  message_count: number;
  platform_count: number;
  platform: Array<{
    name: string;
    count: number;
    timestamp: number;
  }>;
  message_time_series: Array<[number, number]>;
  memory: {
    process: number;
    system: number;
  };
  cpu_percent: number;
  running: {
    hours: number;
    minutes: number;
    seconds: number;
  };
  thread_count: number;
  start_time: number;
}

export interface ProviderTrendItemData {
  name: string;
  data: Array<[number, number]>;
  total_tokens: number;
}

export interface ProviderRankingItemData {
  provider_id: string;
  tokens: number;
}

export interface UmoRankingItemData {
  umo: string;
  tokens: number;
}

export interface ProviderTokenStatsData {
  days: 1 | 3 | 7;
  trend: {
    series: ProviderTrendItemData[];
    total_series: Array<[number, number]>;
  };
  range_total_tokens: number;
  range_total_calls: number;
  range_avg_ttft_ms: number;
  range_avg_duration_ms: number;
  range_avg_tpm: number;
  range_success_rate: number;
  range_by_provider: ProviderRankingItemData[];
  range_by_umo: UmoRankingItemData[];
  today_total_tokens: number;
  today_total_calls: number;
  today_by_provider: ProviderRankingItemData[];
}

export interface BotListParams {
  enabled?: boolean;
  type?: string;
}

export interface ProviderListParams {
  provider_type?:
    | 'chat_completion'
    | 'agent_runner'
    | 'speech_to_text'
    | 'text_to_speech'
    | 'embedding'
    | 'rerank'
    | string;
  provider_source_id?: string;
  enabled?: boolean;
}

export interface ToolListParams {
  origin?: 'builtin' | 'plugin' | 'mcp';
  enabled?: boolean;
}

export interface BackupListParams {
  page?: number;
  page_size?: number;
}

export interface SessionListParams {
  page?: number;
  page_size?: number;
  search?: string;
  platform?: string;
  message_type?: 'all' | 'group' | 'private';
}

export interface SessionRuleListParams {
  page?: number;
  page_size?: number;
  search?: string;
}

export interface ChatSessionListParams {
  page?: number;
  page_size?: number;
  username?: string;
}

export interface CronJobListParams {
  type?: string;
}

type V1Response<T> = Promise<AxiosResponse<ApiEnvelope<T>>>;
type ListConversationsQuery = NonNullable<ListConversationsData['query']>;

function typed<T>(response: Promise<unknown>): V1Response<T> {
  return response as unknown as V1Response<T>;
}

function generatedOptions<T extends Record<string, unknown>>(
  options: T,
  requestConfig?: AxiosRequestConfig,
): T {
  return { ...options, ...(requestConfig || {}) } as T;
}

function generatedQuery<T extends object>(
  params?: T,
): (T & Record<string, unknown>) | undefined {
  return params as (T & Record<string, unknown>) | undefined;
}

function generatedFormData(
  formData: FormData | Record<string, unknown>,
): FormData | Record<string, unknown> {
  if (typeof FormData !== 'undefined' && formData instanceof FormData) {
    const body: Record<string, unknown> = {};
    formData.forEach((value, key) => {
      const existing = body[key];
      if (existing === undefined) {
        body[key] = value;
      } else if (Array.isArray(existing)) {
        existing.push(value);
      } else {
        body[key] = [existing, value];
      }
    });
    return body;
  }
  return formData;
}

function botConfig(config: OpenConfig): BotConfigRequest {
  return {
    config,
  };
}

function providerConfig(config: OpenConfig): ProviderConfigRequest {
  return { config };
}

export const configProfileApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getConfigProfileSchema());
  },
  list() {
    return typed<{ info_list: OpenConfig[] }>(openApiV1.listConfigProfiles());
  },
  create(payload: { name?: string | null; config?: OpenConfig | null }) {
    return typed<{ conf_id: string }>(
      openApiV1.createConfigProfile({
        body: {
          name: payload.name ?? undefined,
          config: payload.config ?? undefined,
        },
      }),
    );
  },
  get(configId: string) {
    return typed<OpenConfig>(
      openApiV1.getConfigProfile({ path: { config_id: configId } }),
    );
  },
  update(
    configId: string,
    config: OpenConfig,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<OpenConfig>(
      openApiV1.updateConfigProfileContent(
        generatedOptions(
          {
            path: { config_id: configId },
            body: config,
          },
          requestConfig,
        ),
      ),
    );
  },
  rename(configId: string, name: string | null) {
    return typed<OpenConfig>(
      openApiV1.renameConfigProfile({
        path: { config_id: configId },
        body: { name: name ?? '' },
      }),
    );
  },
  delete(configId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConfigProfile({ path: { config_id: configId } }),
    );
  },
};

export const systemConfigApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getSystemConfigSchema());
  },
  get() {
    return typed<OpenConfig>(openApiV1.getSystemConfig());
  },
  runtime() {
    return typed<OpenConfig>(openApiV1.getSystemConfigRuntime());
  },
  update(config: OpenConfig, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.updateSystemConfig(
        generatedOptions({ body: config }, requestConfig),
      ),
    );
  },
};

export const configRouteApi = {
  list() {
    return typed<{ routing?: Record<string, string> }>(
      openApiV1.listConfigRoutes(),
    );
  },
  replace(payload: ConfigRoutesReplaceRequest) {
    return typed<OpenConfig>(openApiV1.replaceConfigRoutes({ body: payload }));
  },
  upsert(umo: string, payload: ConfigRouteUpsertRequest) {
    return typed<OpenConfig>(
      openApiV1.upsertConfigRoute({ path: { umo }, body: payload }),
    );
  },
  delete(umo: string) {
    return typed<OpenConfig>(openApiV1.deleteConfigRoute({ path: { umo } }));
  },
};

export const botApi = {
  types() {
    return typed<{ bot_types: OpenConfig[] }>(openApiV1.listBotTypes());
  },
  list(params?: BotListParams) {
    return typed<{ bots: OpenConfig[] }>(
      openApiV1.listBots({ query: generatedQuery(params) }),
    );
  },
  stats() {
    return typed<{ platforms: OpenConfig[] }>(openApiV1.listBotStats());
  },
  registration(botType: string, payload: BotRegistrationRequest) {
    return typed<BotRegistrationData>(
      openApiV1.registerBotType({
        path: { bot_type: botType },
        body: payload,
      }),
    );
  },
  create(config: OpenConfig) {
    return typed<OpenConfig>(openApiV1.createBot({ body: botConfig(config) }));
  },
  get(botId: string) {
    return typed<{ bot: OpenConfig }>(
      openApiV1.getBot({ path: { bot_id: botId } }),
    );
  },
  update(botId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateBot({
        path: { bot_id: botId },
        body: botConfig(config),
      }),
    );
  },
  setEnabled(botId: string, payload: EnabledPatch) {
    return typed<OpenConfig>(
      openApiV1.setBotEnabled({
        path: { bot_id: botId },
        body: payload,
      }),
    );
  },
  delete(botId: string) {
    return typed<OpenConfig>(openApiV1.deleteBot({ path: { bot_id: botId } }));
  },
};

export const providerApi = {
  schema() {
    return typed<ProviderSchemaData>(openApiV1.getProviderSchema());
  },
  sources() {
    return typed<{ provider_sources: OpenConfig[] }>(
      openApiV1.listProviderSources(),
    );
  },
  upsertSource(sourceId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.upsertProviderSource({
        path: { source_id: sourceId },
        body: { config },
      }),
    );
  },
  deleteSource(sourceId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteProviderSource({ path: { source_id: sourceId } }),
    );
  },
  sourceModels(sourceId: string) {
    return typed<ProviderSourceModelsData>(
      openApiV1.listProviderSourceModels({
        path: { source_id: sourceId },
      }),
    );
  },
  list(params?: ProviderListParams) {
    return typed<{ providers: OpenConfig[] }>(
      openApiV1.listProviders({ query: generatedQuery(params) }),
    );
  },
  async listByProviderType(
    providerType: string,
  ): Promise<AxiosResponse<ApiEnvelope<OpenConfig[]>>> {
    const response = await providerApi.list(
      providerType ? { provider_type: providerType } : undefined,
    );
    return {
      ...response,
      data: {
        ...response.data,
        data: response.data.data.providers || [],
      },
    };
  },
  create(config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createProvider({ body: providerConfig(config) }),
    );
  },
  listBySource(
    sourceId: string,
    params?: Pick<ProviderListParams, 'provider_type'>,
  ) {
    return typed<{ providers: OpenConfig[] }>(
      openApiV1.listProvidersBySource({
        path: { source_id: sourceId },
        query: generatedQuery(params),
      }),
    );
  },
  createInSource(sourceId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createProviderInSource({
        path: { source_id: sourceId },
        body: { config },
      }),
    );
  },
  get(providerId: string, merged = false) {
    return typed<{ provider: OpenConfig }>(
      openApiV1.getProvider({
        path: { provider_id: providerId },
        query: { merged },
      }),
    );
  },
  update(providerId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateProvider({
        path: { provider_id: providerId },
        body: { config },
      }),
    );
  },
  setEnabled(providerId: string, payload: EnabledPatch) {
    return typed<OpenConfig>(
      openApiV1.setProviderEnabled({
        path: { provider_id: providerId },
        body: payload,
      }),
    );
  },
  delete(providerId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteProvider({ path: { provider_id: providerId } }),
    );
  },
  test(providerId: string) {
    return typed<ProviderTestData>(
      openApiV1.testProvider({ path: { provider_id: providerId } }),
    );
  },
  embeddingDimension(providerId: string, providerConfig?: OpenConfig) {
    return typed<ProviderEmbeddingDimensionData>(
      openApiV1.getProviderEmbeddingDimension({
        path: { provider_id: providerId },
        body: {
          ...(providerConfig ? { config: providerConfig } : {}),
        },
      }),
    );
  },
};

export const authApi = {
  login(payload: LoginRequest) {
    return typed<AuthLoginData>(openApiV1.login({ body: payload }));
  },
  logout() {
    return typed<OpenConfig>(openApiV1.logout());
  },
  setupStatus(requestConfig?: AxiosRequestConfig) {
    return typed<AuthSetupStatusData>(
      openApiV1.getAuthSetupStatus(generatedOptions({}, requestConfig)),
    );
  },
  setup(payload: SetupAuthRequest) {
    return typed<OpenConfig>(openApiV1.setupAuth({ body: payload }));
  },
  setupTotp(payload?: TotpSetupRequest) {
    return typed<TotpSetupData>(openApiV1.setupTotp({ body: payload }));
  },
  recoverTotp() {
    return typed<TotpSetupData>(openApiV1.recoverTotp());
  },
  updateAccount(payload: UpdateAccountRequest) {
    return typed<OpenConfig>(openApiV1.updateAuthAccount({ body: payload }));
  },
};

export const apiKeyApi = {
  list() {
    return typed<OpenConfig[]>(openApiV1.listApiKeys());
  },
  create(payload: CreateApiKeyRequest) {
    return typed<{ api_key?: string }>(
      openApiV1.createApiKey({ body: payload }),
    );
  },
  revoke(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.revokeApiKey({ path: { key_id: keyId } }),
    );
  },
  delete(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteApiKey({ path: { key_id: keyId } }),
    );
  },
};

export const traceApi = {
  getSettings() {
    return typed<TraceSettingsRequest>(openApiV1.getTraceSettings());
  },
  updateSettings(settings: TraceSettingsRequest) {
    return typed<OpenConfig>(openApiV1.updateTraceSettings({ body: settings }));
  },
};

export const updatesApi = {
  check() {
    return typed<UpdateCheckData>(openApiV1.checkUpdate());
  },
  releases(type?: 'core' | 'dashboard') {
    return typed<ReleaseItemData[]>(
      openApiV1.listReleases({
        query: type ? { type } : undefined,
      }),
    );
  },
  core(payload?: UpdateRequest) {
    return typed<OpenConfig>(openApiV1.updateCore({ body: payload }));
  },
  dashboard(payload?: UpdateRequest) {
    return typed<OpenConfig>(openApiV1.updateDashboard({ body: payload }));
  },
  progress(taskId: string) {
    return typed<UpdateProgressData>(
      openApiV1.getUpdateProgress({ path: { task_id: taskId } }),
    );
  },
  installPip(payload: PipInstallRequest) {
    return typed<OpenConfig>(openApiV1.installPipPackage({ body: payload }));
  },
};

export const backupApi = {
  list(params?: BackupListParams) {
    return typed<OpenConfig>(
      openApiV1.listBackups({ query: generatedQuery(params) }),
    );
  },
  create(payload?: BackupExportRequest) {
    return typed<OpenConfig>(openApiV1.createBackup({ body: payload }));
  },
  progress(taskId: string) {
    return typed<OpenConfig>(
      openApiV1.getBackupProgress({ path: { task_id: taskId } }),
    );
  },
  upload(formData: FormData | BackupUploadRequest) {
    return typed<OpenConfig>(
      openApiV1.uploadBackup({
        body: generatedFormData(formData) as unknown as BackupUploadRequest,
      }),
    );
  },
  initUpload(payload: BackupUploadInitRequest) {
    return typed<OpenConfig>(openApiV1.initBackupUpload({ body: payload }));
  },
  uploadChunk(formData: FormData | BackupChunkUploadRequest) {
    return typed<OpenConfig>(
      openApiV1.uploadBackupChunk({
        body: generatedFormData(
          formData,
        ) as unknown as BackupChunkUploadRequest,
      }),
    );
  },
  completeUpload(payload: BackupUploadSessionRequest) {
    return typed<OpenConfig>(openApiV1.completeBackupUpload({ body: payload }));
  },
  abortUpload(payload: BackupUploadSessionRequest) {
    return typed<OpenConfig>(openApiV1.abortBackupUpload({ body: payload }));
  },
  check(filename: string) {
    return typed<OpenConfig>(openApiV1.checkBackup({ path: { filename } }));
  },
  import(filename: string, confirmed = true) {
    const payload: BackupImportRequest = { confirmed };
    return typed<OpenConfig>(
      openApiV1.importBackup({
        path: { filename },
        body: payload,
      }),
    );
  },
  delete(filename: string) {
    return typed<OpenConfig>(openApiV1.deleteBackup({ path: { filename } }));
  },
  rename(filename: string, payload: BackupRenameRequest) {
    return typed<OpenConfig>(
      openApiV1.renameBackup({ path: { filename }, body: payload }),
    );
  },
  downloadUrl(filename: string, token: string) {
    return `/api/v1/backups/${encodeURIComponent(filename)}?token=${encodeURIComponent(token)}`;
  },
};

export const chatApi = {
  send(payload: ChatRequest) {
    return typed<OpenConfig>(openApiV1.sendChatMessage({ body: payload }));
  },
  sendStreamUrl() {
    return '/api/v1/chat';
  },
  liveWebSocketUrl(token: string, host = window.location.host) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/api/v1/live-chat/ws?token=${encodeURIComponent(token)}`;
  },
  unifiedWebSocketUrl(token: string, host = window.location.host) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/api/v1/unified-chat/ws?token=${encodeURIComponent(token)}`;
  },
  listSessions(params?: ChatSessionListParams) {
    return typed<ChatSessionSummary[]>(
      openApiV1.listChatSessions({ query: generatedQuery(params) }),
    );
  },
  createSession(platformId?: string) {
    return typed<ChatSessionSummary>(
      openApiV1.createChatSession({
        query: platformId ? { platform_id: platformId } : undefined,
      }),
    );
  },
  getSession(sessionId: string) {
    return typed<ChatSessionDetailData>(
      openApiV1.getChatSession({ path: { session_id: sessionId } }),
    );
  },
  updateSession(sessionId: string, payload: ChatSessionPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateChatSession({
        path: { session_id: sessionId },
        body: payload,
      }),
    );
  },
  deleteSession(sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteChatSession({ path: { session_id: sessionId } }),
    );
  },
  batchDeleteSessions(payload: ChatSessionBatchDeleteRequest) {
    return typed<ChatBatchDeleteData>(
      openApiV1.batchDeleteChatSessions({ body: payload }),
    );
  },
  stopSession(sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.stopChatSession({ path: { session_id: sessionId } }),
    );
  },
  updateMessage(
    sessionId: string,
    messageId: string | number,
    payload: ChatMessagePatchRequest,
  ) {
    return typed<ChatMessageMutationData>(
      openApiV1.updateChatMessage({
        path: { session_id: sessionId, message_id: String(messageId) },
        body: payload,
      }),
    );
  },
  regenerateMessage(
    sessionId: string,
    messageId: string | number,
    payload?: ChatMessageRegenerateRequest,
  ) {
    return typed<ChatMessageMutationData>(
      openApiV1.regenerateChatMessage({
        path: { session_id: sessionId, message_id: String(messageId) },
        body: payload,
      }),
    );
  },
  regenerateMessageUrl(sessionId: string, messageId: string | number) {
    return `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(String(messageId))}/regenerate`;
  },
  createThread(payload: ChatThreadCreateRequest) {
    return typed<ChatThreadData>(openApiV1.createChatThread({ body: payload }));
  },
  getThread(threadId: string) {
    return typed<ChatThreadDetailData>(
      openApiV1.getChatThread({ path: { thread_id: threadId } }),
    );
  },
  deleteThread(threadId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteChatThread({ path: { thread_id: threadId } }),
    );
  },
  sendThreadMessage(threadId: string, payload: ChatThreadMessageRequest) {
    return typed<OpenConfig>(
      openApiV1.sendChatThreadMessage({
        path: { thread_id: threadId },
        body: payload,
      }),
    );
  },
  sendThreadMessageUrl(threadId: string) {
    return `/api/v1/chat/threads/${encodeURIComponent(threadId)}/messages`;
  },
  listProjects() {
    return typed<ProjectData[]>(openApiV1.listChatProjects());
  },
  createProject(payload: ChatProjectRequest) {
    return typed<ProjectData>(openApiV1.createChatProject({ body: payload }));
  },
  getProject(projectId: string) {
    return typed<ProjectData>(
      openApiV1.getChatProject({ path: { project_id: projectId } }),
    );
  },
  updateProject(projectId: string, payload: ChatProjectRequest) {
    return typed<ProjectData>(
      openApiV1.updateChatProject({
        path: { project_id: projectId },
        body: payload,
      }),
    );
  },
  deleteProject(projectId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteChatProject({ path: { project_id: projectId } }),
    );
  },
  listProjectSessions(projectId: string) {
    return typed<ChatSessionSummary[]>(
      openApiV1.listChatProjectSessions({ path: { project_id: projectId } }),
    );
  },
  addProjectSession(projectId: string, sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.addChatProjectSession({
        path: { project_id: projectId, session_id: sessionId },
      }),
    );
  },
  removeProjectSession(sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.removeChatProjectSession({ path: { session_id: sessionId } }),
    );
  },
};

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

export const sessionApi = {
  list(params?: SessionListParams) {
    return typed<OpenConfig>(
      openApiV1.listSessions({ query: generatedQuery(params) }),
    );
  },
  activeUmos() {
    return typed<ActiveUmosData>(openApiV1.listActiveUmos());
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
    return typed<OpenConfig[]>(openApiV1.listSessionGroups());
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

export const cronApi = {
  list(params?: CronJobListParams) {
    return typed<OpenConfig[]>(
      openApiV1.listCronJobs({ query: generatedQuery(params) }),
    );
  },
  create(payload: CronJobRequest) {
    return typed<OpenConfig>(openApiV1.createCronJob({ body: payload }));
  },
  update(jobId: string, payload: CronJobPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateCronJob({ path: { job_id: jobId }, body: payload }),
    );
  },
  delete(jobId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteCronJob({ path: { job_id: jobId } }),
    );
  },
  run(jobId: string) {
    return typed<OpenConfig>(openApiV1.runCronJob({ path: { job_id: jobId } }));
  },
};

export const subagentApi = {
  getConfig() {
    return typed<OpenConfig>(openApiV1.getSubagentConfig());
  },
  updateConfig(config: OpenConfig) {
    return typed<OpenConfig>(openApiV1.updateSubagentConfig({ body: config }));
  },
  availableTools() {
    return typed<OpenConfig>(openApiV1.listSubagentAvailableTools());
  },
};

export const commandApi = {
  list(configId?: string) {
    return typed<CommandListData>(
      openApiV1.listCommands({
        query: configId ? { config_id: configId } : undefined,
      }),
    );
  },
  conflicts() {
    return typed<OpenConfig>(openApiV1.listCommandConflicts());
  },
  update(commandId: string, patch: CommandPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateCommand({
        path: { command_id: commandId },
        body: patch,
      }),
    );
  },
};

export const toolApi = {
  list(params?: ToolListParams) {
    return typed<ToolItem[]>(
      openApiV1.listTools({ query: generatedQuery(params) }),
    );
  },
  setEnabled(toolId: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setToolEnabled({
        path: { tool_id: toolId },
        body: { enabled },
      }),
    );
  },
  setPermission(toolId: string, permission: 'admin' | 'member') {
    return typed<OpenConfig>(
      openApiV1.setToolPermission({
        path: { tool_id: toolId },
        body: { permission },
      }),
    );
  },
};

export const mcpApi = {
  list() {
    return typed<OpenConfig[]>(openApiV1.listMcpServers());
  },
  create(config: McpServerConfig) {
    return typed<OpenConfig>(openApiV1.createMcpServer({ body: config }));
  },
  update(serverName: string, config: McpServerConfig) {
    return typed<OpenConfig>(
      openApiV1.updateMcpServer({
        path: { server_name: serverName },
        body: config,
      }),
    );
  },
  delete(serverName: string) {
    return typed<OpenConfig>(
      openApiV1.deleteMcpServer({ path: { server_name: serverName } }),
    );
  },
  setEnabled(serverName: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setMcpServerEnabled({
        path: { server_name: serverName },
        body: { enabled },
      }),
    );
  },
  test(serverName: string, config?: DynamicConfig) {
    return typed<OpenConfig>(
      openApiV1.testMcpServer({
        path: { server_name: serverName },
        body: config ? { config } : undefined,
      }),
    );
  },
  syncModelScope(payload?: ModelScopeSyncRequest) {
    return typed<OpenConfig>(
      openApiV1.syncModelScopeMcpServers({ body: payload }),
    );
  },
};

export const t2iApi = {
  listTemplates() {
    return typed<OpenConfig[]>(openApiV1.listT2iTemplates());
  },
  getTemplate(name: string) {
    return typed<{ name: string; content: string }>(
      openApiV1.getT2iTemplate({ path: { name } }),
    );
  },
  createTemplate(payload: T2iTemplateRequest) {
    return typed<OpenConfig>(openApiV1.createT2iTemplate({ body: payload }));
  },
  updateTemplate(name: string, content: string) {
    return typed<OpenConfig>(
      openApiV1.updateT2iTemplate({
        path: { name },
        body: { content },
      }),
    );
  },
  deleteTemplate(name: string) {
    return typed<OpenConfig>(openApiV1.deleteT2iTemplate({ path: { name } }));
  },
  getActiveTemplate() {
    return typed<{ active_template?: string }>(
      openApiV1.getActiveT2iTemplate(),
    );
  },
  setActiveTemplate(name: string) {
    return typed<OpenConfig>(
      openApiV1.setActiveT2iTemplate({ body: { name } }),
    );
  },
  resetDefaultTemplate() {
    return typed<OpenConfig>(openApiV1.resetDefaultT2iTemplate());
  },
};

export const logApi = {
  history() {
    return typed<{ logs?: OpenConfig[] }>(openApiV1.getLogHistory());
  },
  liveUrl() {
    return '/api/v1/logs/live';
  },
};

export const pluginApi = {
  list(params?: { include_reserved?: boolean; enabled?: boolean }) {
    return typed<PluginData[]>(openApiV1.listPlugins({ query: params }));
  },
  get(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPlugin({ path: { plugin_id: pluginId } }),
    );
  },
  failed() {
    return typed<Record<string, OpenConfig>>(openApiV1.listFailedPlugins());
  },
  reloadFailed(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.reloadFailedPlugin({ path: { plugin_id: pluginId } }),
    );
  },
  uninstallFailed(
    pluginId: string,
    options?: { delete_config?: boolean; delete_data?: boolean },
  ) {
    return typed<OpenConfig>(
      openApiV1.uninstallFailedPlugin({
        path: { plugin_id: pluginId },
        body: options,
      }),
    );
  },
  uninstall(
    pluginId: string,
    options?: { delete_config?: boolean; delete_data?: boolean },
  ) {
    return typed<OpenConfig>(
      openApiV1.uninstallPlugin({
        path: { plugin_id: pluginId },
        body: options,
      }),
    );
  },
  reload(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.reloadPlugin({ path: { plugin_id: pluginId } }),
    );
  },
  setEnabled(pluginId: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setPluginEnabled({
        path: { plugin_id: pluginId },
        body: { enabled },
      }),
    );
  },
  update(pluginId: string, body?: PluginUpdateRequest) {
    return typed<OpenConfig>(
      openApiV1.updatePlugin({
        path: { plugin_id: pluginId },
        body,
      }),
    );
  },
  updateMany(body: PluginBatchUpdateRequest) {
    return typed<OpenConfig>(openApiV1.updatePlugins({ body }));
  },
  config(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginConfig({ path: { plugin_id: pluginId } }),
    );
  },
  updateConfig(pluginId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePluginConfig({
        path: { plugin_id: pluginId },
        body: { config },
      }),
    );
  },
  listConfigFiles(pluginId: string, configKey: string) {
    return typed<PluginConfigFilesData>(
      openApiV1.listPluginConfigFiles({
        path: { plugin_id: pluginId, config_key: configKey },
      }),
    );
  },
  uploadConfigFiles(pluginId: string, configKey: string, formData: FormData) {
    return typed<PluginConfigUploadData>(
      openApiV1.uploadPluginConfigFiles({
        path: { plugin_id: pluginId, config_key: configKey },
        body: generatedFormData(formData) as Record<string, unknown>,
      }),
    );
  },
  deleteConfigFile(pluginId: string, payload: PluginConfigFileDeleteRequest) {
    return typed<OpenConfig>(
      openApiV1.deletePluginConfigFile({
        path: { plugin_id: pluginId },
        body: payload,
      }),
    );
  },
  readme(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginReadme({ path: { plugin_id: pluginId } }),
    );
  },
  changelog(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginChangelog({ path: { plugin_id: pluginId } }),
    );
  },
  market(params?: {
    page?: number;
    page_size?: number;
    category?: string;
    sort?: 'recommended' | 'downloads' | 'updated' | 'name';
    keyword?: string;
    force_refresh?: boolean;
    custom_registry?: string;
  }) {
    return typed<OpenConfig>(openApiV1.listPluginMarket({ query: params }));
  },
  sources() {
    return typed<PluginSourceRequest[]>(openApiV1.listPluginSources());
  },
  replaceSources(sources: PluginSourceRequest[]) {
    return typed<OpenConfig>(
      openApiV1.replacePluginSources({ body: { sources } }),
    );
  },
  installUpload(formData: FormData) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromUpload({
        body: generatedFormData(
          formData,
        ) as unknown as PluginUploadInstallRequest,
      }),
    );
  },
  installGithub(body: PluginGithubInstallRequest) {
    return typed<OpenConfig>(openApiV1.installPluginFromGithub({ body }));
  },
  installUrl(body: PluginUrlInstallRequest) {
    return typed<OpenConfig>(openApiV1.installPluginFromUrl({ body }));
  },
  bindSource(pluginId: string, body: PluginSourceBindRequest) {
    return typed<OpenConfig>(
      openApiV1.bindPluginSource({
        path: { plugin_id: pluginId },
        body,
      }),
    );
  },
};

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
  create(config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.createKnowledgeBase({ body: config as never }),
    );
  },
  update(kbId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateKnowledgeBase({
        path: { kb_id: kbId },
        body: config as never,
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

export const skillApi = {
  list(params?: { enabled?: boolean; source?: string }) {
    return typed<SkillListData>(openApiV1.listSkills({ query: params }));
  },
  uploadBatch(files: File[]) {
    return typed<OpenConfig>(openApiV1.uploadSkillsBatch({ body: { files } }));
  },
  setEnabled(skillName: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.updateSkill({
        path: { skill_name: skillName },
        body: { active: enabled },
      }),
    );
  },
  delete(skillName: string) {
    return typed<OpenConfig>(
      openApiV1.deleteSkill({ path: { skill_name: skillName } }),
    );
  },
  download(skillName: string) {
    return openApiV1.downloadSkill({
      path: { skill_name: skillName },
      responseType: 'blob',
    });
  },
  listFiles(skillName: string, path = '') {
    return typed<OpenConfig>(
      openApiV1.listSkillFiles({
        path: { skill_name: skillName },
        query: path ? { path } : undefined,
      }),
    );
  },
  getFile(skillName: string, path: string) {
    return typed<OpenConfig>(
      openApiV1.getSkillFile({
        path: { skill_name: skillName, file_path: path },
      }),
    );
  },
  updateFile(skillName: string, path: string, content: string) {
    return typed<OpenConfig>(
      openApiV1.updateSkillFile({
        path: { skill_name: skillName, file_path: path },
        body: content,
      }),
    );
  },
  neoCandidates(params?: { skill_key?: string; status?: string }) {
    return typed<OpenConfig>(
      openApiV1.listNeoSkillCandidates({ query: params }),
    );
  },
  neoReleases(params?: { skill_key?: string; stage?: string }) {
    return typed<OpenConfig>(openApiV1.listNeoSkillReleases({ query: params }));
  },
  neoPayload(payloadRef: string) {
    return typed<OpenConfig>(
      openApiV1.getNeoSkillPayload({ query: { payload_ref: payloadRef } }),
    );
  },
  evaluateNeoCandidate(body: NeoCandidateActionRequest) {
    return typed<OpenConfig>(openApiV1.evaluateNeoSkillCandidate({ body }));
  },
  promoteNeoCandidate(body: NeoCandidateActionRequest) {
    return typed<OpenConfig>(openApiV1.promoteNeoSkillCandidate({ body }));
  },
  rollbackNeoRelease(body: NeoReleaseActionRequest) {
    return typed<OpenConfig>(openApiV1.rollbackNeoSkillRelease({ body }));
  },
  syncNeoRelease(body: NeoReleaseActionRequest) {
    return typed<OpenConfig>(openApiV1.syncNeoSkillRelease({ body }));
  },
  deleteNeoCandidate(body: NeoCandidateActionRequest) {
    return typed<OpenConfig>(openApiV1.deleteNeoSkillCandidate({ body }));
  },
  deleteNeoRelease(body: NeoReleaseActionRequest) {
    return typed<OpenConfig>(openApiV1.deleteNeoSkillRelease({ body }));
  },
};

export const personaApi = {
  tree() {
    return typed<PersonaFolderData[]>(openApiV1.getPersonaTree());
  },
  folders(parentId?: string | null) {
    return typed<PersonaFolderData[]>(
      openApiV1.listPersonaFolders({
        query:
          parentId === undefined ? undefined : { parent_id: parentId ?? '' },
      }),
    );
  },
  createFolder(folder: PersonaFolderInput) {
    return typed<OpenConfig>(
      openApiV1.createPersonaFolder({
        body: folder as unknown as PersonaFolderRequest,
      }),
    );
  },
  updateFolder(folderId: string, folder: PersonaFolderInput) {
    return typed<OpenConfig>(
      openApiV1.updatePersonaFolder({
        path: { folder_id: folderId },
        body: folder as unknown as PersonaFolderRequest,
      }),
    );
  },
  deleteFolder(folderId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePersonaFolder({ path: { folder_id: folderId } }),
    );
  },
  list(folderId?: string | null) {
    return typed<PersonaData[]>(
      openApiV1.listPersonas({
        query:
          folderId === undefined ? undefined : { folder_id: folderId ?? '' },
      }),
    );
  },
  get(personaId: string) {
    return typed<PersonaData>(
      openApiV1.getPersona({ path: { persona_id: personaId } }),
    );
  },
  create(persona: PersonaInput) {
    return typed<OpenConfig>(
      openApiV1.createPersona({ body: persona as unknown as PersonaRequest }),
    );
  },
  update(personaId: string, persona: Omit<PersonaInput, 'persona_id'>) {
    return typed<OpenConfig>(
      openApiV1.updatePersona({
        path: { persona_id: personaId },
        body: persona as unknown as PersonaRequest,
      }),
    );
  },
  delete(personaId: string) {
    return typed<OpenConfig>(
      openApiV1.deletePersona({ path: { persona_id: personaId } }),
    );
  },
  move(personaId: string, folderId: string | null) {
    const payload: PersonaMoveRequest = {
      persona_id: personaId,
      folder_id: folderId ?? undefined,
    };
    return typed<OpenConfig>(openApiV1.movePersonaItem({ body: payload }));
  },
  reorder(items: ReorderRequest['items']) {
    return typed<OpenConfig>(
      openApiV1.reorderPersonaItems({ body: { items } }),
    );
  },
};

export const conversationApi = {
  list(params?: ListConversationsQuery, requestConfig?: AxiosRequestConfig) {
    return typed<ConversationListResponseData>(
      openApiV1.listConversations(
        generatedOptions({ query: generatedQuery(params) }, requestConfig),
      ),
    );
  },
  get(userId: string, cid: string) {
    return typed<ConversationRecordData>(
      openApiV1.getConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
      }),
    );
  },
  update(userId: string, cid: string, payload: ConversationPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
        body: payload,
      }),
    );
  },
  replaceMessages(
    userId: string,
    cid: string,
    payload: ConversationMessagesReplaceRequest,
  ) {
    return typed<OpenConfig>(
      openApiV1.replaceConversationMessages({
        path: { conversation_id: cid },
        query: { user_id: userId },
        body: payload,
      }),
    );
  },
  delete(userId: string, cid: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
      }),
    );
  },
  batchDelete(payload: ConversationBatchDeleteRequest) {
    return typed<ConversationBatchDeleteData>(
      openApiV1.batchDeleteConversations({ body: payload }),
    );
  },
  export(payload: ConversationExportRequest) {
    return openApiV1.exportConversations({
      body: payload,
      responseType: 'blob',
    }) as Promise<AxiosResponse<Blob>>;
  },
};

export const statsApi = {
  get(offsetSec?: number) {
    return typed<BaseStatsData>(
      openApiV1.getStats({
        query: offsetSec === undefined ? undefined : { offset_sec: offsetSec },
      }),
    );
  },
  providerTokens(days?: number) {
    return typed<ProviderTokenStatsData>(
      openApiV1.getProviderTokenStats({
        query: days === undefined ? undefined : { days },
      }),
    );
  },
  version(requestConfig?: AxiosRequestConfig) {
    return typed<VersionData>(
      openApiV1.getVersion(generatedOptions({}, requestConfig)),
    );
  },
  firstNotice(locale?: string) {
    return typed<{ content?: string | null }>(
      openApiV1.getFirstNotice({
        query: locale ? { locale } : undefined,
      }),
    );
  },
  testGhproxy(payload: GhproxyTestRequest) {
    return typed<{ latency?: number }>(
      openApiV1.testGhproxyConnection({ body: payload }),
    );
  },
  startTime(requestConfig?: AxiosRequestConfig) {
    return typed<StartTimeData>(
      openApiV1.getStartTime(generatedOptions({}, requestConfig)),
    );
  },
  restart(requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.restartCore(generatedOptions({}, requestConfig)),
    );
  },
  storage() {
    return typed<OpenConfig>(openApiV1.getStorageStatus());
  },
  cleanupStorage(target?: string) {
    return typed<OpenConfig>(
      openApiV1.cleanupStorage({
        body: target ? { target } : undefined,
      }),
    );
  },
};

export const publicApi = {
  versions(requestConfig?: AxiosRequestConfig) {
    return typed<PublicVersionData>(
      openApiV1.getPublicVersions(generatedOptions({}, requestConfig)),
    );
  },
};

export const changelogApi = {
  listVersions() {
    return typed<{ versions?: string[] }>(openApiV1.listChangelogVersions());
  },
  get(version: string) {
    return typed<{ content?: string }>(
      openApiV1.getChangelog({ path: { version } }),
    );
  },
};

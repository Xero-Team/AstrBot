import { computed, onBeforeUnmount, reactive, ref } from 'vue';
import { chatApi, fileApi } from '@/api/v1';
import { fetchWithAuth } from '@/api/http';
import { useI18n } from '@/i18n/composables';
import type { Session } from '@/composables/useSessions';
import type {
  BranchGroup,
  ChatContent,
  ChatRecord,
  ChatSessionProject,
  HistoryRecord,
  MessagePart,
} from '@/domain/chat';
import { buildChatRequestFlags } from './chatRequestFlags';
import { createStreamPayloadHandlers } from './chatStreamPayload';
import { readSseStream } from './chatStreamReader';
import {
  cloneContentWithEditedText,
  extractReasoningText,
  isUserMessage,
  messageContent,
  messageParts,
  normalizeMessageParts,
  normalizeSessionProject,
  partToPayload,
  stripUploadOnlyFields,
} from './messageContent';
import {
  attachThreads,
  mergeHistoryRecords,
  normalizeBranchGroup,
} from './messageHistory';
import { appendPlain } from './messageRecordMutations';
import type {
  ActiveChatRun,
  ActiveConnection,
  ContinueEditedMessageOptions,
  CreateLocalExchangeOptions,
  HistoryPaginationState,
  SendMessageStreamOptions,
  UseMessagesOptions,
} from './messagesTypes';

export type { HistoryPaginationState, TransportMode } from './messagesTypes';
export {
  displayParts,
  extractReasoningText,
  messageBlocks,
  normalizeMessageParts,
  reasoningActivityCounts,
  reasoningActivityTitle,
  thinkingParts,
} from './messageContent';
export { mergeHistoryRecords } from './messageHistory';
export {
  appendCompletePlainSuffix,
  appendPlain,
  appendReasoningPart,
  finishToolCall,
  hasPlainText,
  markMessageStarted,
  parseJsonSafe,
  payloadText,
  upsertToolCall,
} from './messageRecordMutations';

/** Manage request-scoped chat messages, history pages, and live transports. */
export function useMessages(options: UseMessagesOptions) {
  const { locale } = useI18n();
  const loadingMessagesState = ref(false);
  const sending = ref(false);
  const messagesBySession = reactive(new Map<string, ChatRecord[]>());
  const loadedSessions = reactive(new Map<string, boolean>());
  const paginationBySession = reactive(
    new Map<string, HistoryPaginationState>(),
  );
  const activeConnections = reactive<Record<string, ActiveConnection>>({});
  const chatWebSockets = new Map<string, WebSocket>();
  const closingChatWebSockets = new WeakSet<WebSocket>();
  const deferredBotAnchors = new WeakMap<ChatRecord, ChatRecord>();
  const attachmentBlobCache = new Map<string, Promise<string>>();
  const sessionLoadEpochs = reactive(new Map<string, number>());
  const loadingSessionId = ref<string | null>(null);
  const sessionProjects = reactive(
    new Map<string, ChatSessionProject | null>(),
  );
  // Session metadata returned with a session load, used to keep an opened
  // session visible in the sidebar before its paginated page is fetched.
  const sessionDetails = reactive(new Map<string, Session>());

  const branchSelection = reactive(new Map<string, number>());
  const branchLabels = reactive(new Map<string, string[]>());

  const activeMessages = computed(() => {
    const sessionId = options.currentSessionId.value;
    if (!sessionId) return [];
    const records = messagesBySession.get(sessionId) || [];
    return records.filter((record) => {
      const group = record.branchGroup;
      if (!group) return true;
      const selected = branchSelection.get(group.group_id) ?? 0;
      return group.index === selected;
    });
  });
  const loadingMessages = computed(
    () =>
      loadingMessagesState.value &&
      loadingSessionId.value === options.currentSessionId.value,
  );

  const { processStreamPayload, ensureBotRecordVisible } =
    createStreamPayloadHandlers({
      activeConnections,
      getRecords: (sessionId) => messagesBySession.get(sessionId) || [],
      resolvePartMedia,
      resolveRecordMedia,
      normalizeHistoryRecord,
      clearWebChatStepUpTokens,
    });

  onBeforeUnmount(() => {
    cleanupConnections();
    for (const promise of attachmentBlobCache.values()) {
      promise
        .then((url) => void URL.revokeObjectURL(url))
        .catch(() => undefined);
    }
    attachmentBlobCache.clear();
  });

  function isSessionRunning(sessionId: string) {
    return Object.values(activeConnections).some(
      (connection) => connection.sessionId === sessionId,
    );
  }

  function isMessageStreaming(msg: ChatRecord, _msgIndex: number) {
    const sessionId = options.currentSessionId.value;
    if (!sessionId || isUserMessage(msg)) return false;
    return Object.values(activeConnections).some(
      (connection) =>
        connection.sessionId === sessionId &&
        connection.botVisible !== false &&
        (connection.botRecord === msg ||
          (connection.botRecord?.id !== null &&
            connection.botRecord?.id !== undefined &&
            String(connection.botRecord.id) === String(msg.id))),
    );
  }

  async function resolvePartMedia(part: MessagePart): Promise<void> {
    if (part.embedded_url) return;
    let url: string;
    let cacheKey: string;
    const storedFilename =
      typeof part.stored_filename === 'string' ? part.stored_filename : '';
    const lookupFilename = storedFilename || part.filename || '';
    if (part.attachment_id) {
      cacheKey = `att:${part.attachment_id}`;
      url = fileApi.contentUrl(part.attachment_id);
    } else if (lookupFilename) {
      cacheKey = `file:${lookupFilename}`;
      url = '';
    } else {
      return;
    }
    let promise = attachmentBlobCache.get(cacheKey);
    if (!promise) {
      if (!part.attachment_id && lookupFilename) {
        promise = fileApi
          .getByName(lookupFilename)
          .then((resp) => URL.createObjectURL(resp.data));
      } else {
        promise = fetchWithAuth(url).then(async (resp) => {
          if (!resp.ok) throw new Error(`Media request failed: ${resp.status}`);
          return URL.createObjectURL(await resp.blob());
        });
      }
      attachmentBlobCache.set(cacheKey, promise);
    }
    try {
      part.embedded_url = await promise;
    } catch (e) {
      attachmentBlobCache.delete(cacheKey);
      console.error('Failed to resolve media:', cacheKey, e);
    }
  }

  async function resolveRecordMedia(records: ChatRecord[]) {
    const mediaTypes = ['image', 'record', 'video'];
    const tasks: Promise<void>[] = [];
    for (const record of records) {
      for (const part of record.content?.message || []) {
        if (
          mediaTypes.includes(part.type) &&
          !part.embedded_url &&
          (part.attachment_id || part.stored_filename || part.filename)
        ) {
          tasks.push(resolvePartMedia(part));
        }
      }
    }
    await Promise.all(tasks);
  }

  function commitLoadedSession(
    sessionId: string,
    records: ChatRecord[],
    payload: Record<string, unknown>,
    preserveLoadedPages: boolean,
  ) {
    const previousPagination = paginationBySession.get(sessionId);
    const existing = messagesBySession.get(sessionId) || [];
    if (preserveLoadedPages && existing.length) {
      const merged = mergeHistoryRecords(existing, records);
      messagesBySession.set(sessionId, merged);
      const total =
        Number(payload.total) || previousPagination?.total || merged.length;
      const pageSize =
        Number(payload.page_size) || previousPagination?.page_size || 50;
      paginationBySession.set(sessionId, {
        page: Math.max(1, previousPagination?.page || 1),
        page_size: pageSize,
        total,
        has_more: merged.length < total,
        loading: false,
        error: undefined,
      });
      return;
    }
    messagesBySession.set(sessionId, records);
    paginationBySession.set(sessionId, {
      page: Number(payload.page) || 1,
      page_size: Number(payload.page_size) || 50,
      total: Number(payload.total) || records.length,
      has_more: Boolean(payload.has_more),
      loading: false,
    });
  }

  function recordSessionLoadError(sessionId: string, error: unknown) {
    console.error('Failed to load session messages:', error);
    const existing = messagesBySession.get(sessionId) || [];
    messagesBySession.set(sessionId, existing);
    const previousPagination = paginationBySession.get(sessionId);
    paginationBySession.set(sessionId, {
      page: previousPagination?.page || 1,
      page_size: previousPagination?.page_size || 50,
      total: previousPagination?.total || existing.length,
      has_more: previousPagination?.has_more || false,
      loading: false,
      error: String((error as Error)?.message || error),
    });
  }

  async function loadSessionMessages(
    sessionId: string,
    resumeRuns = true,
    showLoading = true,
    preserveLoadedPages = false,
  ) {
    if (!sessionId) return;
    if (showLoading) {
      loadingMessagesState.value = true;
      loadingSessionId.value = sessionId;
    }
    const epoch = (sessionLoadEpochs.get(sessionId) || 0) + 1;
    sessionLoadEpochs.set(sessionId, epoch);
    try {
      const response = await chatApi.getSession(sessionId, {
        page: 1,
        page_size: 50,
      });
      const status = response.data?.status;
      if (status && status !== 'ok') {
        throw new Error(
          response.data?.message || 'Failed to load session messages',
        );
      }
      const payload = response.data?.data || {};
      const history = payload.history || [];
      const records: ChatRecord[] = history.map((record) =>
        normalizeHistoryRecord(record),
      );
      attachThreads(records, payload.threads || []);
      await resolveRecordMedia(records);
      if (sessionLoadEpochs.get(sessionId) !== epoch) return;
      commitLoadedSession(sessionId, records, payload, preserveLoadedPages);
      sessionProjects.set(sessionId, normalizeSessionProject(payload.project));
      const sessionMeta = payload.session;
      if (sessionMeta?.session_id === sessionId) {
        sessionDetails.set(sessionId, sessionMeta);
      }
      loadedSessions.set(sessionId, true);
      if (resumeRuns && Array.isArray(payload.active_runs)) {
        await restoreNextActiveRun(sessionId, payload.active_runs);
      }
    } catch (error) {
      if (sessionLoadEpochs.get(sessionId) !== epoch) return;
      recordSessionLoadError(sessionId, error);
    } finally {
      if (
        showLoading &&
        sessionLoadEpochs.get(sessionId) === epoch &&
        loadingSessionId.value === sessionId
      ) {
        loadingMessagesState.value = false;
        loadingSessionId.value = null;
      }
    }
  }

  async function loadEarlierMessages(sessionId: string) {
    if (!sessionId) return;
    const state = paginationBySession.get(sessionId);
    if (!state || !state.has_more || state.loading) return;
    const epoch = sessionLoadEpochs.get(sessionId) || 0;
    const nextPage = state.page + 1;
    state.loading = true;
    state.error = undefined;
    try {
      const response = await chatApi.getSession(sessionId, {
        page: nextPage,
        page_size: state.page_size,
      });
      if (sessionLoadEpochs.get(sessionId) !== epoch) return;
      const status = response.data?.status;
      if (status && status !== 'ok') {
        throw new Error(
          response.data?.message || 'Failed to load earlier messages',
        );
      }
      const payload = response.data?.data || {};
      const records = (payload.history || []).map(normalizeHistoryRecord);
      attachThreads(records, payload.threads || []);
      await resolveRecordMedia(records);
      if (sessionLoadEpochs.get(sessionId) !== epoch) return;
      const existing = messagesBySession.get(sessionId) || [];
      const merged = mergeHistoryRecords(existing, records);
      messagesBySession.set(sessionId, merged);
      state.page = Number(payload.page) || nextPage;
      state.total = Number(payload.total) || state.total;
      state.has_more = merged.length < state.total && records.length > 0;
    } catch (error) {
      if (sessionLoadEpochs.get(sessionId) !== epoch) return;
      state.error = String((error as Error)?.message || error);
      console.error('Failed to load earlier session messages:', error);
    } finally {
      if (sessionLoadEpochs.get(sessionId) === epoch) state.loading = false;
    }
  }

  async function restoreNextActiveRun(
    sessionId: string,
    activeRuns: ActiveChatRun[],
  ) {
    const run = activeRuns[0];
    if (!run?.run_id || isSessionRunning(sessionId)) return;

    const checkpointId = run.llm_checkpoint_id || null;
    const records = (messagesBySession.get(sessionId) || []).filter(
      (record) => {
        return !(
          checkpointId &&
          record.llm_checkpoint_id === checkpointId &&
          messageContent(record).type === 'bot'
        );
      },
    );
    const botRecord = normalizeHistoryRecord({
      id: `active-run-${run.run_id}`,
      content: run.content || { type: 'bot', message: [] },
      llm_checkpoint_id: checkpointId,
      created_at: new Date().toISOString(),
    });
    botRecord.content.isLoading = botRecord.content.message.length === 0;
    records.push(botRecord);
    messagesBySession.set(sessionId, records);
    const restoredRecords = messagesBySession.get(sessionId) || records;
    const reactiveBotRecord = restoredRecords[restoredRecords.length - 1];
    await resolveRecordMedia([reactiveBotRecord]);
    startResumeStream(sessionId, run.run_id, reactiveBotRecord);
  }

  function createLocalExchange({
    sessionId,
    messageId,
    parts,
  }: CreateLocalExchangeOptions) {
    loadedSessions.set(sessionId, true);
    if (!messagesBySession.get(sessionId)) {
      messagesBySession.set(sessionId, []);
    }

    const userRecord = reactive<ChatRecord>({
      id: `local-user-${messageId}`,
      created_at: new Date().toISOString(),
      content: {
        type: 'user',
        message: parts.map(stripUploadOnlyFields),
      },
    });

    const botRecord = reactive<ChatRecord>({
      id: `local-bot-${messageId}`,
      created_at: new Date().toISOString(),
      content: {
        type: 'bot',
        message: [],
        reasoning: '',
        isLoading: true,
      },
    });

    const sessionMessages = messagesBySession.get(sessionId) || [];
    if (isSessionRunning(sessionId)) {
      const activeBotConnections = Object.values(activeConnections).filter(
        (connection) =>
          connection.sessionId === sessionId &&
          connection.botVisible !== false &&
          connection.botRecord &&
          sessionMessages.includes(connection.botRecord),
      );
      const activeBotRecord =
        activeBotConnections[activeBotConnections.length - 1]?.botRecord;
      if (activeBotRecord) {
        const activeBotIndex = sessionMessages.indexOf(activeBotRecord);
        sessionMessages.splice(activeBotIndex, 0, userRecord);
        deferredBotAnchors.set(botRecord, activeBotRecord);
      } else {
        sessionMessages.push(userRecord);
      }
    } else {
      sessionMessages.push(userRecord, botRecord);
    }

    return {
      userRecord,
      botRecord,
    };
  }

  /** Create and append a branch bot record for one model of a parallel turn. */
  function createLocalBranchRecord(
    sessionId: string,
    messageId: string,
    branch: BranchGroup,
  ): ChatRecord {
    const botRecord = reactive<ChatRecord>({
      id: `local-bot-${messageId}`,
      created_at: new Date().toISOString(),
      content: {
        type: 'bot',
        message: [],
        reasoning: '',
        isLoading: true,
      },
      branchGroup: branch,
    });
    const sessionMessages = messagesBySession.get(sessionId) || [];
    sessionMessages.push(botRecord);
    messagesBySession.set(sessionId, sessionMessages);
    registerBranchLabel(branch);
    return botRecord;
  }

  function setBranchSelection(groupId: string, index: number) {
    branchSelection.set(groupId, index);
  }

  function sendMessageStream({
    sessionId,
    messageId,
    parts,
    transport,
    enableStreaming = true,
    enableReasoning = true,
    selectedProvider = '',
    selectedModel = '',
    botRecord,
    userRecord,
    skipUserHistory = false,
    llmCheckpointId = null,
    branch,
  }: SendMessageStreamOptions) {
    // Step-up credentials are one-time per action.  Take the in-memory bundle
    // at run creation so a later chat cannot replay an already consumed proof.
    const stepUpTokens = takeWebChatStepUpTokens();
    if (transport === 'websocket' && !branch) {
      startWebSocketStream(
        sessionId,
        messageId,
        parts,
        botRecord,
        userRecord,
        enableStreaming,
        enableReasoning,
        selectedProvider,
        selectedModel,
        stepUpTokens,
      );
      return;
    }
    startSseStream(
      sessionId,
      messageId,
      parts,
      botRecord,
      userRecord,
      enableStreaming,
      enableReasoning,
      selectedProvider,
      selectedModel,
      skipUserHistory,
      llmCheckpointId,
      stepUpTokens,
      branch,
    );
  }

  function takeWebChatStepUpTokens(): Record<string, string> | undefined {
    const tokens = options.webchatStepUpTokens?.value || undefined;
    if (tokens && options.webchatStepUpTokens) {
      options.webchatStepUpTokens.value = null;
    }
    return tokens;
  }

  function clearWebChatStepUpTokens() {
    if (options.webchatStepUpTokens) {
      options.webchatStepUpTokens.value = null;
    }
  }

  async function editMessage(
    sessionId: string,
    record: ChatRecord,
    editedText: string,
  ) {
    if (!sessionId || record.id === undefined || record.id === null) {
      return { needsRegenerate: false };
    }
    const content = cloneContentWithEditedText(record, editedText);
    const response = await chatApi.updateMessage(sessionId, record.id, {
      content: content as unknown as Record<string, unknown>,
    });
    const payload = response.data?.data || {};
    const updated = payload.message
      ? normalizeHistoryRecord(payload.message)
      : null;
    if (updated) {
      Object.assign(record, updated);
      await resolveRecordMedia([record]);
    }
    if (payload.truncated_after_message) {
      truncateMessagesAfter(sessionId, record);
      const pagination = paginationBySession.get(sessionId);
      if (pagination) {
        pagination.page = 0;
        pagination.error = undefined;
      }
      await loadSessionMessages(sessionId, false, false, true);
    }
    return {
      needsRegenerate: Boolean(payload.needs_regenerate),
      truncatedAfterMessage: Boolean(payload.truncated_after_message),
    };
  }

  function truncateMessagesAfter(sessionId: string, record: ChatRecord) {
    const records = messagesBySession.get(sessionId);
    if (!records?.length || record.id === undefined || record.id === null) {
      return;
    }
    const index = records.findIndex(
      (message) => String(message.id) === String(record.id),
    );
    if (index < 0) return;
    messagesBySession.set(sessionId, records.slice(0, index + 1));
  }

  function continueEditedMessage({
    sessionId,
    sourceRecord,
    enableStreaming = true,
    enableReasoning = true,
    selectedProvider = '',
    selectedModel = '',
  }: ContinueEditedMessageOptions) {
    if (!sessionId) return;
    const parts = messageParts(sourceRecord).map(stripUploadOnlyFields);
    const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    if (!messagesBySession.get(sessionId)) {
      messagesBySession.set(sessionId, []);
    }

    const botRecord: ChatRecord = {
      id: `local-edited-bot-${messageId}`,
      created_at: new Date().toISOString(),
      content: {
        type: 'bot',
        message: [],
        reasoning: '',
        isLoading: true,
      },
    };
    messagesBySession.get(sessionId)?.push(botRecord);

    const stepUpTokens = takeWebChatStepUpTokens();
    startSseStream(
      sessionId,
      messageId,
      parts,
      botRecord,
      undefined,
      enableStreaming,
      enableReasoning,
      selectedProvider,
      selectedModel,
      true,
      sourceRecord.llm_checkpoint_id || null,
      stepUpTokens,
    );
  }

  async function regenerateMessage(
    sessionId: string,
    botRecord: ChatRecord,
    selectedProvider = '',
    selectedModel = '',
    enableStreaming = true,
    enableReasoning = true,
  ) {
    if (!sessionId || botRecord.id === undefined || botRecord.id === null) {
      return;
    }
    const targetMessageId = botRecord.id;

    botRecord.id = `local-regenerate-${Date.now()}`;
    botRecord.created_at = new Date().toISOString();
    botRecord.content = {
      type: 'bot',
      message: [],
      reasoning: '',
      isLoading: true,
    };

    const abort = new AbortController();
    const connection: ActiveConnection = {
      sessionId,
      messageId: String(botRecord.id),
      transport: 'sse',
      abort,
      botRecord,
      botVisible: true,
    };
    activeConnections[connection.messageId] = connection;
    const stepUpTokens = takeWebChatStepUpTokens();

    try {
      const response = await fetchWithAuth(
        chatApi.regenerateMessageUrl(sessionId, targetMessageId),
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            selected_provider: selectedProvider,
            selected_model: selectedModel,
            flags: buildChatRequestFlags(enableStreaming, enableReasoning),
            locale: locale.value,
            _webchat_step_up_tokens: stepUpTokens,
          }),
          signal: abort.signal,
        },
      );
      if (!response.ok || !response.body) {
        throw new Error(`Regenerate failed: ${response.status}`);
      }
      const contentType = response.headers.get('content-type') || '';
      if (!contentType.includes('text/event-stream')) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.message || 'Regenerate failed.');
      }
      clearWebChatStepUpTokens();
      await readSseStream(response.body, (payload) => {
        processStreamPayload(botRecord, payload, undefined, connection);
        options.onStreamUpdate?.(sessionId);
      });
    } catch (error) {
      if (!abort.signal.aborted) {
        appendPlain(
          botRecord,
          `\n\n${String((error as Error)?.message || error)}`,
        );
        console.error('Regenerate failed:', error);
      }
    } finally {
      if (activeConnections[connection.messageId]?.abort === abort) {
        delete activeConnections[connection.messageId];
      }
      await options.onSessionsChanged?.();
    }
  }

  async function stopSession(sessionId: string) {
    if (!sessionId) return;
    await chatApi.stopSession(sessionId);
  }

  function cleanupConnections() {
    Object.values(activeConnections).forEach((connection) => {
      connection.abort?.abort();
    });
    chatWebSockets.forEach(closeTrackedWebSocket);
    Object.keys(activeConnections).forEach((messageId) => {
      delete activeConnections[messageId];
    });
    chatWebSockets.clear();
    if (options.webchatStepUpTokens) {
      options.webchatStepUpTokens.value = null;
    }
  }

  function normalizeHistoryRecord(record: HistoryRecord): ChatRecord {
    const content = record.content || {};
    const normalizedMessage = normalizeMessageParts(
      content.message || [],
      content.reasoning || '',
    );
    const normalizedContent: ChatContent = {
      type: content.type || (record.sender_id === 'bot' ? 'bot' : 'user'),
      message: normalizedMessage,
      reasoning: extractReasoningText(
        normalizedMessage,
        content.reasoning || '',
      ),
      agentStats: content.agentStats || content.agent_stats,
      refs: content.refs,
    };

    const branchGroup = normalizeBranchGroup(content.branch);
    if (branchGroup) {
      registerBranchLabel(branchGroup);
    }
    return {
      ...record,
      content: normalizedContent,
      ...(branchGroup ? { branchGroup } : {}),
    };
  }

  function registerBranchLabel(group: BranchGroup) {
    const labels = branchLabels.get(group.group_id) || [];
    labels[group.index] =
      group.model || group.provider || `#${group.index + 1}`;
    branchLabels.set(group.group_id, labels);
  }

  function startSseStream(
    sessionId: string,
    messageId: string,
    parts: MessagePart[],
    botRecord: ChatRecord,
    userRecord: ChatRecord | undefined,
    enableStreaming: boolean,
    enableReasoning: boolean,
    selectedProvider: string,
    selectedModel: string,
    skipUserHistory = false,
    llmCheckpointId: string | null = null,
    stepUpTokens?: Record<string, string>,
    branch?: BranchGroup,
  ) {
    const abort = new AbortController();
    const connection: ActiveConnection = {
      sessionId,
      messageId,
      transport: 'sse',
      abort,
      botRecord,
      userRecord,
      botVisible:
        messagesBySession.get(sessionId)?.includes(botRecord) ?? false,
      deferredBeforeBot: deferredBotAnchors.get(botRecord),
    };
    activeConnections[messageId] = connection;

    fetchWithAuth(chatApi.sendStreamUrl(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id: sessionId,
        message_id: messageId,
        message: parts.map(partToPayload),
        flags: buildChatRequestFlags(enableStreaming, enableReasoning),
        selected_provider: selectedProvider,
        selected_model: selectedModel,
        locale: locale.value,
        _skip_user_history: skipUserHistory,
        _llm_checkpoint_id: llmCheckpointId || undefined,
        _webchat_step_up_tokens: stepUpTokens,
        _branch: branch || undefined,
      }),
      signal: abort.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }
        clearWebChatStepUpTokens();
        await readSseStream(response.body, (payload) => {
          processStreamPayload(botRecord, payload, userRecord, connection);
          options.onStreamUpdate?.(sessionId);
        });
      })
      .catch((error) => {
        if (abort.signal.aborted) return;
        ensureBotRecordVisible(connection);
        appendPlain(botRecord, `\n\n${String(error?.message || error)}`);
        console.error('SSE chat failed:', error);
      })
      .finally(async () => {
        if (activeConnections[messageId]?.abort === abort) {
          delete activeConnections[messageId];
          await options.onSessionsChanged?.();
        }
      });
  }

  function delayWithAbort(ms: number, signal: AbortSignal): Promise<void> {
    return new Promise<void>((resolve) => {
      const timeout = window.setTimeout(resolve, ms);
      signal.addEventListener(
        'abort',
        () => {
          window.clearTimeout(timeout);
          resolve();
        },
        { once: true },
      );
    });
  }

  async function finalizeResumeConnection(
    runId: string,
    abort: AbortController,
    sessionId: string,
  ) {
    const ownsConnection = activeConnections[runId]?.abort === abort;
    if (ownsConnection) delete activeConnections[runId];
    if (abort.signal.aborted || !ownsConnection) return;
    if (!isSessionRunning(sessionId)) {
      await loadSessionMessages(sessionId, true, false, true);
    }
    await options.onSessionsChanged?.();
  }

  function startResumeStream(
    sessionId: string,
    runId: string,
    botRecord: ChatRecord,
  ) {
    const abort = new AbortController();
    const connection: ActiveConnection = {
      sessionId,
      messageId: runId,
      runId,
      transport: 'sse',
      abort,
      botRecord,
      botVisible: true,
    };
    activeConnections[runId] = connection;

    void (async () => {
      let receivedEnd = false;
      let lastError: unknown = null;

      for (
        let attempt = 0;
        attempt < 5 && !abort.signal.aborted;
        attempt += 1
      ) {
        let retryable = true;
        try {
          const response = await fetchWithAuth(
            chatApi.resumeRunStreamUrl(runId),
            {
              headers: { Accept: 'text/event-stream' },
              signal: abort.signal,
            },
          );
          const contentType = response.headers.get('content-type') || '';
          if (
            !response.ok ||
            !response.body ||
            !contentType.includes('text/event-stream')
          ) {
            retryable = response.status >= 500;
            throw new Error(`Resume stream failed: ${response.status}`);
          }

          await readSseStream(response.body, (payload) => {
            processStreamPayload(botRecord, payload, undefined, connection);
            options.onStreamUpdate?.(sessionId);
            const payloadType = payload?.type || payload?.t;
            if (payloadType === 'end') receivedEnd = true;
          });
          if (receivedEnd) break;
          lastError = new Error('Resume stream closed before completion.');
        } catch (error) {
          if (abort.signal.aborted) return;
          lastError = error;
        }

        if (!retryable || attempt === 4 || abort.signal.aborted) break;
        await delayWithAbort(250 * 2 ** attempt, abort.signal);
      }

      if (!receivedEnd && lastError && !abort.signal.aborted) {
        console.error('Resume chat stream failed:', lastError);
      }

      await finalizeResumeConnection(runId, abort, sessionId);
    })();
  }

  function startWebSocketStream(
    sessionId: string,
    messageId: string,
    parts: MessagePart[],
    botRecord: ChatRecord,
    userRecord: ChatRecord | undefined,
    enableStreaming: boolean,
    enableReasoning: boolean,
    selectedProvider: string,
    selectedModel: string,
    stepUpTokens?: Record<string, string>,
  ) {
    const ws = getOrCreateChatWebSocket(sessionId);

    const connection: ActiveConnection = {
      sessionId,
      messageId,
      transport: 'websocket',
      ws,
      botRecord,
      userRecord,
      completed: false,
      errorShown: false,
      botVisible:
        messagesBySession.get(sessionId)?.includes(botRecord) ?? false,
      deferredBeforeBot: deferredBotAnchors.get(botRecord),
    };
    activeConnections[messageId] = connection;

    sendWebSocketPayload(sessionId, messageId, {
      ct: 'chat',
      t: 'send',
      session_id: sessionId,
      message_id: messageId,
      message: parts.map(partToPayload),
      flags: buildChatRequestFlags(enableStreaming, enableReasoning),
      selected_provider: selectedProvider,
      selected_model: selectedModel,
      locale: locale.value,
      webchat_step_up_tokens: stepUpTokens,
    });
  }

  function getWebSocketConnections(sessionId: string, ws?: WebSocket) {
    return Object.values(activeConnections).filter(
      (connection) =>
        connection.sessionId === sessionId &&
        connection.transport === 'websocket' &&
        (!ws || connection.ws === ws),
    );
  }

  function getOrCreateChatWebSocket(sessionId: string) {
    const existing = chatWebSockets.get(sessionId);
    if (
      existing &&
      (existing.readyState === WebSocket.OPEN ||
        existing.readyState === WebSocket.CONNECTING)
    ) {
      return existing;
    }

    const token = localStorage.getItem('token') || '';
    const ws = new WebSocket(chatApi.unifiedWebSocketUrl(token));
    chatWebSockets.set(sessionId, ws);

    ws.onmessage = (event) => {
      handleWebSocketMessage(sessionId, event);
    };
    ws.onerror = () => {
      for (const connection of getWebSocketConnections(sessionId, ws)) {
        if (!connection.botRecord) continue;
        connection.errorShown = true;
        ensureBotRecordVisible(connection);
        appendPlain(connection.botRecord, '\n\nWebSocket connection failed.');
      }
    };
    ws.onclose = async () => {
      if (chatWebSockets.get(sessionId) === ws) {
        chatWebSockets.delete(sessionId);
      }

      const connections = getWebSocketConnections(sessionId, ws);
      for (const connection of connections) {
        if (
          !connection.completed &&
          !connection.errorShown &&
          !closingChatWebSockets.has(ws) &&
          connection.botRecord
        ) {
          ensureBotRecordVisible(connection);
          appendPlain(connection.botRecord, '\n\nWebSocket connection closed.');
        }
        delete activeConnections[connection.messageId];
      }
      if (connections.length) await options.onSessionsChanged?.();
    };
    return ws;
  }

  function sendWebSocketPayload(
    sessionId: string,
    messageId: string,
    payload: Record<string, unknown>,
  ) {
    const ws = getOrCreateChatWebSocket(sessionId);
    const send = () => {
      const connection = activeConnections[messageId];
      if (
        connection?.transport !== 'websocket' ||
        connection.messageId !== messageId ||
        connection.ws !== ws
      ) {
        return;
      }
      try {
        ws.send(JSON.stringify(payload));
      } catch (error) {
        connection.errorShown = true;
        if (connection.botRecord) {
          ensureBotRecordVisible(connection);
          appendPlain(connection.botRecord, '\n\nWebSocket connection failed.');
        }
        console.error('Failed to send WebSocket payload:', error);
        void finishWebSocketStream(sessionId, messageId);
      }
    };

    if (ws.readyState === WebSocket.OPEN) {
      send();
      return;
    }
    if (ws.readyState === WebSocket.CONNECTING) {
      ws.addEventListener('open', send, { once: true });
      return;
    }
    void finishWebSocketStream(sessionId, messageId);
  }

  function handleWebSocketMessage(sessionId: string, event: MessageEvent) {
    try {
      const payload = JSON.parse(event.data);
      const payloadMessageId =
        payload?.message_id === null || payload?.message_id === undefined
          ? ''
          : String(payload.message_id);
      let connection = payloadMessageId
        ? activeConnections[payloadMessageId]
        : undefined;
      if (!connection) {
        connection = getWebSocketConnections(sessionId)[0];
      }
      if (connection?.transport !== 'websocket' || !connection.botRecord) {
        return;
      }
      const messageType = payload?.type || payload?.t;
      if (messageType === 'mcp_input_request') {
        options.onMcpInputRequest?.(payload, (response) => {
          sendWebSocketPayload(sessionId, connection.messageId, {
            t: 'mcp_input_response',
            ...response,
            request_id: payload.request_id || payload.message_id,
            message_id: payload.message_id,
            run_id: payload.run_id,
            server_name: payload.server_name,
            unified_msg_origin: payload.unified_msg_origin,
          });
        });
        return;
      }
      processStreamPayload(
        connection.botRecord,
        payload,
        connection.userRecord,
        connection,
      );
      options.onStreamUpdate?.(sessionId);
      if (payload.type === 'end' || payload.t === 'end') {
        void finishWebSocketStream(sessionId, connection.messageId);
      }
    } catch (error) {
      console.error('Failed to parse WebSocket payload:', error);
    }
  }

  async function finishWebSocketStream(sessionId: string, messageId: string) {
    const connection = activeConnections[messageId];
    if (
      connection?.transport !== 'websocket' ||
      connection.messageId !== messageId
    ) {
      return;
    }
    connection.completed = true;
    delete activeConnections[messageId];
    await options.onSessionsChanged?.();
  }

  function closeTrackedWebSocket(ws: WebSocket) {
    closingChatWebSockets.add(ws);
    if (
      ws.readyState === WebSocket.OPEN ||
      ws.readyState === WebSocket.CONNECTING
    ) {
      ws.close();
    }
  }

  return {
    loadingMessages,
    sending,
    messagesBySession,
    loadedSessions,
    paginationBySession,
    sessionProjects,
    sessionDetails,
    activeMessages,
    isSessionRunning,
    isUserMessage,
    isMessageStreaming,
    messageContent,
    messageParts,
    loadSessionMessages,
    loadEarlierMessages,
    createLocalExchange,
    createLocalBranchRecord,
    branchSelection,
    branchLabels,
    setBranchSelection,
    sendMessageStream,
    editMessage,
    continueEditedMessage,
    regenerateMessage,
    stopSession,
    cleanupConnections,
  };
}

<template>
  <div class="session-management-page">
    <v-container fluid class="pa-4 pa-md-6">
      <header class="page-header">
        <div class="page-header__copy">
          <h1 class="page-header__title">
            {{ tm('title') }}
            <ConfigDocsLink docs="use/custom-rules.html" />
          </h1>
          <p class="page-header__subtitle">{{ tm('subtitle') }}</p>
        </div>
        <div class="page-header__actions">
          <v-chip size="small" variant="outlined">
            {{ totalItems }} {{ tm('customRules.rulesCount') }}
          </v-chip>
          <v-btn
            color="primary"
            prepend-icon="mdi-refresh"
            variant="text"
            :loading="loading"
            @click="refreshData"
          >
            {{ tm('buttons.refresh') }}
          </v-btn>
        </div>
      </header>

      <v-card flat>
        <div class="session-rules-toolbar">
          <v-btn-toggle
            v-model="targetType"
            density="compact"
            variant="outlined"
            divided
            mandatory
          >
            <v-btn size="small" value="session">{{
              tm('targetType.session')
            }}</v-btn>
            <v-btn size="small" value="sender">{{
              tm('targetType.sender')
            }}</v-btn>
          </v-btn-toggle>
          <v-text-field
            v-model="searchQuery"
            class="session-rules-toolbar__search"
            prepend-inner-icon="mdi-magnify"
            :label="
              isSenderTarget
                ? tm('search.senderPlaceholder')
                : tm('search.placeholder')
            "
            hide-details
            clearable
            variant="solo-filled"
            flat
            density="compact"
          ></v-text-field>
          <div class="session-rules-toolbar__actions">
            <v-btn
              v-if="selectedItems.length > 0"
              color="error"
              prepend-icon="mdi-delete"
              variant="tonal"
              size="small"
              @click="confirmBatchDelete"
            >
              {{ tm('buttons.batchDelete') }} ({{ selectedItems.length }})
            </v-btn>
            <v-btn
              color="success"
              prepend-icon="mdi-plus"
              variant="tonal"
              size="small"
              @click="openAddRuleDialog"
            >
              {{ tm('buttons.addRule') }}
            </v-btn>
          </div>
        </div>

        <v-divider></v-divider>

        <p class="table-scroll-hint session-rules-scroll-hint">
          <v-icon size="14" aria-hidden="true"
            >mdi-gesture-swipe-horizontal</v-icon
          >
          {{ tm('table.scrollHint') }}
        </p>

        <v-card-text class="pa-0">
          <SessionRulesTable
            v-model:items-per-page="itemsPerPage"
            v-model:page="currentPage"
            v-model:selected-items="selectedItems"
            :headers="headers"
            :items="filteredRulesList"
            :loading="loading"
            :items-length="totalItems"
            :item-value="tableItemValue"
            :is-sender-target="isSenderTarget"
            :items-per-page-options="[10, 25, 50, 100]"
            @update:options="onTableOptionsUpdate"
            @edit-rule="openRuleEditor"
            @delete-rules="confirmDeleteRules"
            @edit-custom-name="openQuickEditName"
            @add-rule="openAddRuleDialog"
          />
        </v-card-text>
      </v-card>
      <!-- 批量操作面板 -->
      <v-card v-if="!isSenderTarget" flat class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-title-small">{{
            tm('batchOperations.title')
          }}</span>
          <v-chip size="small" class="ml-2" color="info" variant="outlined">
            {{ tm('batchOperations.hint') }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <v-row density="comfortable">
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchScope"
                :items="batchScopeOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.scope')"
                hide-details
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchLlmStatus"
                :items="statusOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.llmStatus')"
                hide-details
                clearable
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchTtsStatus"
                :items="statusOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.ttsStatus')"
                hide-details
                clearable
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchChatProvider"
                :items="batchChatProviderOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.chatProvider')"
                hide-details
                clearable
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
          </v-row>
          <v-row class="mt-3" density="comfortable">
            <v-col cols="12" class="d-flex justify-end">
              <v-btn
                color="primary"
                variant="tonal"
                size="large"
                :disabled="!canApplyBatch"
                :loading="batchUpdating"
                prepend-icon="mdi-check-all"
                @click="applyBatchChanges"
              >
                {{ tm('batchOperations.apply') }}
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 分组管理面板 -->
      <v-card v-if="!isSenderTarget" flat class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-title-small">{{ tm('groups.title') }}</span>
          <v-chip
            size="small"
            class="ml-2"
            color="secondary"
            variant="outlined"
          >
            {{ tm('groups.count', { count: groups.length }) }}
          </v-chip>
          <v-spacer></v-spacer>
          <v-btn
            v-if="selectedItems.length > 0 && groups.length > 0"
            color="info"
            variant="tonal"
            size="small"
            class="mr-2"
          >
            <v-icon start>mdi-folder-plus</v-icon>
            {{ tm('groups.addToGroup') }}
            <v-menu activator="parent">
              <v-list density="compact">
                <v-list-item
                  v-for="g in groups"
                  :key="g.id"
                  @click="addSelectedToGroup(g.id)"
                >
                  <v-list-item-title>{{
                    tm('groups.customGroupOption', {
                      name: g.name,
                      count: g.umo_count,
                    })
                  }}</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
          </v-btn>
          <v-btn
            color="success"
            variant="tonal"
            size="small"
            prepend-icon="mdi-folder-plus"
            @click="openCreateGroupDialog"
          >
            {{ tm('groups.create') }}
          </v-btn>
        </v-card-title>
        <v-card-text v-if="groups.length > 0">
          <v-row density="comfortable">
            <v-col
              v-for="group in groups"
              :key="group.id"
              cols="12"
              sm="6"
              md="4"
              lg="3"
            >
              <v-card variant="outlined" class="pa-3">
                <div class="d-flex align-center justify-space-between">
                  <div>
                    <div class="font-weight-bold">{{ group.name }}</div>
                    <div class="text-caption text-medium-emphasis">
                      {{
                        tm('groups.sessionsCount', { count: group.umo_count })
                      }}
                    </div>
                  </div>
                  <div>
                    <v-btn
                      icon
                      size="small"
                      variant="text"
                      :aria-label="tm('buttons.edit')"
                      @click="openEditGroupDialog(group)"
                    >
                      <v-icon size="small">mdi-pencil</v-icon>
                    </v-btn>
                    <v-btn
                      icon
                      size="small"
                      variant="text"
                      color="error"
                      :aria-label="tm('buttons.delete')"
                      @click="deleteGroup(group)"
                    >
                      <v-icon size="small">mdi-delete</v-icon>
                    </v-btn>
                  </div>
                </div>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-text v-else class="text-center text-medium-emphasis py-6">
          {{ tm('groups.empty') }}
        </v-card-text>
      </v-card>

      <!-- 分组编辑对话框 -->
      <SessionGroupDialog
        v-model="groupDialog"
        :mode="groupDialogMode"
        :name="editingGroup.name"
        :selected-umos="editingGroup.umos"
        :unselected-umos="unselectedUmos"
        :loading-umos="loadingUmos"
        :member-search="groupMemberSearch"
        :selected-search="groupSelectedSearch"
        :umo-info-map="availableUmoInfoMap"
        @update:name="updateGroupName"
        @update:member-search="updateGroupMemberSearch"
        @update:selected-search="updateGroupSelectedSearch"
        @add-umo="addToGroup"
        @remove-umo="removeFromGroup"
        @add-all="addAllToGroup"
        @remove-all="removeAllFromGroup"
        @save="saveGroup"
        @load-available="loadAvailableUmos"
      />

      <!-- 添加规则对话框 - 选择 UMO -->
      <SessionAddRuleDialog
        v-model="addRuleDialog"
        v-model:selected-new-umo="selectedNewUmo"
        v-model:selected-new-sender-id="selectedNewSenderId"
        :is-sender-target="isSenderTarget"
        :available-umos="availableUmos"
        :loading-umos="loadingUmos"
        :umo-info-map="availableUmoInfoMap"
        @create="createNewRule"
      />

      <!-- 规则编辑对话框 -->
      <SessionRuleEditorDialog
        v-model="ruleDialog"
        :selected-umo="selectedUmo"
        :saving="saving"
        :sender-overlay="senderOverlay"
        :service-config="serviceConfig"
        :provider-config="providerConfig"
        :plugin-config="pluginConfig"
        :kb-config="kbConfig"
        :chat-provider-options="chatProviderOptions"
        :stt-provider-options="sttProviderOptions"
        :tts-provider-options="ttsProviderOptions"
        :prompt-options="promptOptions"
        :plugin-options="pluginOptions"
        :kb-options="kbOptions"
        :has-stt-providers="availableSttProviders.length > 0"
        :has-tts-providers="availableTtsProviders.length > 0"
        :has-kbs="availableKbs.length > 0"
        @save-service-config="saveServiceConfig"
        @save-provider-config="saveProviderConfig"
        @save-plugin-config="savePluginConfig"
        @save-kb-config="saveKbConfig"
        @close="closeRuleEditor"
      />

      <!-- 确认删除对话框 -->
      <SessionDeleteConfirmDialog
        v-model="deleteDialog"
        :target="deleteTarget"
        :deleting="deleting"
        @confirm="deleteAllRules"
      />

      <!-- 批量删除确认对话框 -->
      <SessionBatchDeleteDialog
        v-model="batchDeleteDialog"
        :selected-items="selectedItems"
        :deleting="deleting"
        :umo-info-map="availableUmoInfoMap"
        @confirm="batchDeleteRules"
      />

      <!-- 提示信息 -->
      <v-snackbar
        v-model="snackbar"
        :timeout="3000"
        elevation="4"
        :color="snackbarColor"
        location="top"
      >
        {{ snackbarText }}
      </v-snackbar>

      <!-- 快速编辑备注名对话框 -->
      <SessionQuickEditNameDialog
        v-model="quickEditNameDialog"
        v-model:value="quickEditNameValue"
        :saving="saving"
        @save="saveQuickEditName"
      />
    </v-container>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { sessionApi } from '@/api/v1';
import type {
  BatchSessionProviderRequest,
  BatchSessionServiceRequest,
} from '@/api/generated/openapi-v1';
import ConfigDocsLink from '@/components/shared/ConfigDocsLink.vue';
import { useModuleI18n } from '@/i18n/composables';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import SessionGroupDialog from './session-management/SessionGroupDialog.vue';
import SessionAddRuleDialog from './session-management/SessionAddRuleDialog.vue';
import SessionRuleEditorDialog from './session-management/SessionRuleEditorDialog.vue';
import SessionDeleteConfirmDialog from './session-management/SessionDeleteConfirmDialog.vue';
import SessionBatchDeleteDialog from './session-management/SessionBatchDeleteDialog.vue';
import SessionQuickEditNameDialog from './session-management/SessionQuickEditNameDialog.vue';
import SessionRulesTable from './session-management/SessionRulesTable.vue';
import {
  buildBatchTargetPayload,
  clearProviderRule,
  getProviderRule,
  isSenderRule,
  isSenderSubjectId,
  normalizeBoolean,
  normalizeGroup,
  normalizeKnowledgeBaseOption,
  normalizeNumber,
  normalizePluginOption,
  normalizePromptOption,
  normalizeProviderOption,
  normalizeRuleItem,
  normalizeString,
  normalizeStringArray,
  normalizeUmoInfo,
  resolveUmoInfo,
  sessionAliasName,
  setProviderRule,
  toRuleValue,
  unwrittenServiceEnabled,
} from './session-management/sessionRuleNormalizers';
import {
  FOLLOW_CONFIG_VALUE,
  type BatchScope,
  type DebouncedCallback,
  type GroupDialogMode,
  type GroupEditorState,
  type GroupItem,
  type KnowledgeBaseOption,
  type PluginOption,
  type PromptOption,
  type ProviderOption,
  type ProviderRuleType,
  type RuleKey,
  type RuleTargetType,
  type SelectOption,
  type SenderOverlayState,
  type SessionKbConfig,
  type SessionPluginConfig,
  type SessionRuleItem,
  type SessionRuleSet,
  type SessionServiceConfig,
  type SnackbarColor,
  type TableOptionsLike,
  type UmoDisplayInfo,
} from './session-management/sessionRuleHelpers';

const { tm } = useModuleI18n('features/session-management');
const confirmDialog = useConfirmDialog();

const loading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const loadingUmos = ref(false);
const rulesList = ref<SessionRuleItem[]>([]);
const searchQuery = ref('');
const targetType = ref<RuleTargetType>('session');
const isSenderTarget = computed(() => targetType.value === 'sender');
const tableItemValue = computed(() =>
  isSenderTarget.value ? 'sender_id' : 'umo',
);

const currentPage = ref(1);
const itemsPerPage = ref(10);
const totalItems = ref(0);

const availablePrompts = ref<PromptOption[]>([]);
const availableChatProviders = ref<ProviderOption[]>([]);
const availableSttProviders = ref<ProviderOption[]>([]);
const availableTtsProviders = ref<ProviderOption[]>([]);
const availablePlugins = ref<PluginOption[]>([]);
const availableKbs = ref<KnowledgeBaseOption[]>([]);

const addRuleDialog = ref(false);
const availableUmos = ref<string[]>([]);
const availableUmoInfoMap = ref<Record<string, UmoDisplayInfo>>({});
const selectedNewUmo = ref<string | null>(null);
const selectedNewSenderId = ref('');

const ruleDialog = ref(false);
const selectedUmo = ref<SessionRuleItem | null>(null);
const editingRules = ref<SessionRuleSet>({});

const senderOverlay = reactive<SenderOverlayState>({
  blocked: false,
  llm_enabled: null,
});

const serviceConfig = reactive<
  Required<
    Pick<
      SessionServiceConfig,
      'session_enabled' | 'llm_enabled' | 'tts_enabled' | 'session_blocked'
    >
  > & {
    custom_name: string;
    prompt_id: string | null;
  }
>({
  session_enabled: false,
  llm_enabled: false,
  tts_enabled: false,
  session_blocked: false,
  custom_name: '',
  prompt_id: null,
});

const providerConfig = reactive<Record<ProviderRuleType, string>>({
  chat_completion: FOLLOW_CONFIG_VALUE,
  speech_to_text: FOLLOW_CONFIG_VALUE,
  text_to_speech: FOLLOW_CONFIG_VALUE,
});

const pluginConfig = reactive<
  Required<Pick<SessionPluginConfig, 'enabled_plugins' | 'disabled_plugins'>>
>({
  enabled_plugins: [],
  disabled_plugins: [],
});

const kbConfig = reactive<
  Required<Pick<SessionKbConfig, 'kb_ids' | 'top_k' | 'enable_rerank'>>
>({
  kb_ids: [],
  top_k: 5,
  enable_rerank: true,
});

const deleteDialog = ref(false);
const deleteTarget = ref<SessionRuleItem | null>(null);

const selectedItems = ref<SessionRuleItem[]>([]);
const batchDeleteDialog = ref(false);

const quickEditNameDialog = ref(false);
const quickEditNameTarget = ref<SessionRuleItem | null>(null);
const quickEditNameValue = ref('');

const batchScope = ref<BatchScope>('selected');
const batchLlmStatus = ref<boolean | null>(null);
const batchTtsStatus = ref<boolean | null>(null);
const batchChatProvider = ref<string | null>(null);
const batchTtsProvider = ref<string | null>(null);
const batchUpdating = ref(false);

const groups = ref<GroupItem[]>([]);
const groupsLoading = ref(false);
const groupDialog = ref(false);
const groupDialogMode = ref<GroupDialogMode>('create');
const editingGroup = reactive<GroupEditorState>({
  id: null,
  name: '',
  umos: [],
});
const groupMemberSearch = ref('');
const groupSelectedSearch = ref('');

const snackbar = ref(false);
const snackbarText = ref('');
const snackbarColor = ref<SnackbarColor>('success');

const headers = computed(() => [
  {
    title: isSenderTarget.value
      ? tm('table.headers.senderInfo')
      : tm('table.headers.umoInfo'),
    key: 'umo_info',
    sortable: false,
    minWidth: '300px',
  },
  {
    title: tm('table.headers.rulesOverview'),
    key: 'rules_overview',
    sortable: false,
    minWidth: '250px',
  },
  {
    title: tm('table.headers.actions'),
    key: 'actions',
    sortable: false,
    minWidth: '150px',
  },
]);

const filteredRulesList = computed(() => rulesList.value);

const promptOptions = computed<SelectOption<string | null>[]>(() => [
  { label: tm('prompt.none'), value: null },
  ...availablePrompts.value.map((prompt) => ({
    label: prompt.name,
    value: prompt.name,
  })),
]);

const chatProviderOptions = computed<SelectOption<string>[]>(() => [
  { label: tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
  ...availableChatProviders.value.map((provider) => ({
    label: `${provider.name} (${provider.model || ''})`,
    value: provider.id,
  })),
]);

const sttProviderOptions = computed<SelectOption<string>[]>(() => [
  { label: tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
  ...availableSttProviders.value.map((provider) => ({
    label: `${provider.name} (${provider.model || ''})`,
    value: provider.id,
  })),
]);

const ttsProviderOptions = computed<SelectOption<string>[]>(() => [
  { label: tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
  ...availableTtsProviders.value.map((provider) => ({
    label: `${provider.name} (${provider.model || ''})`,
    value: provider.id,
  })),
]);

const batchChatProviderOptions = computed(() => chatProviderOptions.value);

const pluginOptions = computed<SelectOption<string>[]>(() =>
  availablePlugins.value.map((plugin) => ({
    label: plugin.display_name || plugin.name,
    value: plugin.name,
  })),
);

const kbOptions = computed<SelectOption<string>[]>(() =>
  availableKbs.value.map((kb) => ({
    label: `${kb.emoji || '📚'} ${kb.kb_name}`,
    value: kb.kb_id,
  })),
);

const batchScopeOptions = computed<SelectOption<string>[]>(() => {
  const options: SelectOption<string>[] = [
    { label: tm('batchOperations.scopeSelected'), value: 'selected' },
    { label: tm('batchOperations.scopeAll'), value: 'all' },
    { label: tm('batchOperations.scopeGroup'), value: 'group' },
    { label: tm('batchOperations.scopePrivate'), value: 'private' },
  ];

  if (groups.value.length > 0) {
    options.push({
      label: tm('groups.customGroupDivider'),
      value: '_divider',
      disabled: true,
    });
    groups.value.forEach((group) => {
      options.push({
        label: tm('groups.customGroupOption', {
          name: group.name,
          count: group.umo_count,
        }),
        value: `custom_group:${group.id}`,
      });
    });
  }

  return options;
});

const statusOptions = computed<SelectOption<boolean>[]>(() => [
  { label: tm('status.enabled'), value: true },
  { label: tm('status.disabled'), value: false },
]);

const canApplyBatch = computed(() => {
  const hasChanges =
    batchLlmStatus.value !== null ||
    batchTtsStatus.value !== null ||
    batchChatProvider.value !== null ||
    batchTtsProvider.value !== null;

  if (batchScope.value === 'selected') {
    return hasChanges && selectedItems.value.length > 0;
  }

  return hasChanges;
});

const unselectedUmos = computed(() => {
  const selected = new Set(editingGroup.umos);
  return availableUmos.value.filter((umo) => !selected.has(umo));
});

const debouncedSearch = createDebouncedCallback(() => {
  currentPage.value = 1;
  void loadData();
}, 300);

watch(searchQuery, () => {
  debouncedSearch();
});

watch(targetType, () => {
  currentPage.value = 1;
  selectedItems.value = [];
  void loadData();
});

onMounted(() => {
  void loadData();
  void loadGroups();
});

onBeforeUnmount(() => {
  debouncedSearch.cancel();
});

function createDebouncedCallback(
  callback: () => void,
  delayMs: number,
): DebouncedCallback {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const debounced = (() => {
    if (timer) {
      clearTimeout(timer);
    }

    timer = setTimeout(() => {
      timer = null;
      callback();
    }, delayMs);
  }) as DebouncedCallback;

  debounced.cancel = () => {
    if (!timer) {
      return;
    }

    clearTimeout(timer);
    timer = null;
  };

  return debounced;
}

function mergeUmoInfos(infos: unknown) {
  const next = { ...availableUmoInfoMap.value };
  if (!Array.isArray(infos)) {
    availableUmoInfoMap.value = next;
    return;
  }

  infos.forEach((info) => {
    const normalized = normalizeUmoInfo(info);
    if (normalized?.umo) {
      next[normalized.umo] = { ...(next[normalized.umo] || {}), ...normalized };
    }
  });

  availableUmoInfoMap.value = next;
}

function getAvailableUmoInfo(value: unknown): UmoDisplayInfo {
  return resolveUmoInfo(value, availableUmoInfoMap.value);
}

function buildUmoItem(
  umo: string,
  rules: SessionRuleSet = {},
): SessionRuleItem {
  const info = getAvailableUmoInfo(umo);
  return {
    ...info,
    umo,
    rules,
  };
}

function findRuleItem(umo: string): SessionRuleItem | undefined {
  return rulesList.value.find((item) => item.umo === umo);
}

function ensureRuleItem(umo: string): SessionRuleItem {
  const existing = findRuleItem(umo);
  if (existing) {
    return existing;
  }

  const next = buildUmoItem(umo);
  rulesList.value.push(next);
  return next;
}

function resetGroupEditor() {
  editingGroup.id = null;
  editingGroup.name = '';
  editingGroup.umos = [];
  groupMemberSearch.value = '';
  groupSelectedSearch.value = '';
}

function updateGroupName(value: string) {
  editingGroup.name = value;
}

function updateGroupMemberSearch(value: string) {
  groupMemberSearch.value = value;
}

function updateGroupSelectedSearch(value: string) {
  groupSelectedSearch.value = value;
}

async function loadData() {
  loading.value = true;
  try {
    const response = await sessionApi.listRules({
      page: currentPage.value,
      page_size: itemsPerPage.value,
      search: searchQuery.value || '',
      target_type: targetType.value,
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.loadError'));
      return;
    }

    const data = response.data.data;
    const normalizedRules = Array.isArray(data.rules)
      ? data.rules
          .map((item) => normalizeRuleItem(item))
          .filter((item): item is SessionRuleItem => item !== null)
      : [];

    rulesList.value = normalizedRules;
    mergeUmoInfos(data.rules);
    totalItems.value = normalizeNumber(data.total, 0);
    availablePrompts.value = Array.isArray(data.available_prompts)
      ? data.available_prompts
          .map((item) => normalizePromptOption(item))
          .filter((item): item is PromptOption => item !== null)
      : [];
    availableChatProviders.value = Array.isArray(data.available_chat_providers)
      ? data.available_chat_providers
          .map((item) => normalizeProviderOption(item))
          .filter((item): item is ProviderOption => item !== null)
      : [];
    availableSttProviders.value = Array.isArray(data.available_stt_providers)
      ? data.available_stt_providers
          .map((item) => normalizeProviderOption(item))
          .filter((item): item is ProviderOption => item !== null)
      : [];
    availableTtsProviders.value = Array.isArray(data.available_tts_providers)
      ? data.available_tts_providers
          .map((item) => normalizeProviderOption(item))
          .filter((item): item is ProviderOption => item !== null)
      : [];
    availablePlugins.value = Array.isArray(data.available_plugins)
      ? data.available_plugins
          .map((item) => normalizePluginOption(item))
          .filter((item): item is PluginOption => item !== null)
      : [];
    availableKbs.value = Array.isArray(data.available_kbs)
      ? data.available_kbs
          .map((item) => normalizeKnowledgeBaseOption(item))
          .filter((item): item is KnowledgeBaseOption => item !== null)
      : [];
  } catch {
    showError(tm('messages.loadError'));
  } finally {
    loading.value = false;
  }
}

function onTableOptionsUpdate(options: TableOptionsLike) {
  if (typeof options.page === 'number') {
    currentPage.value = options.page;
  }
  if (typeof options.itemsPerPage === 'number') {
    itemsPerPage.value = options.itemsPerPage;
  }
  void loadData();
}

async function loadUmos() {
  loadingUmos.value = true;
  try {
    const response = await sessionApi.activeUmos();
    if (response.data.status !== 'ok') {
      return;
    }

    mergeUmoInfos(response.data.data.umo_infos);
    const existingUmos = new Set(rulesList.value.map((item) => item.umo));
    const allUmos = normalizeStringArray(response.data.data.umos);
    availableUmos.value = allUmos.filter((umo) => !existingUmos.has(umo));
  } catch {
    showError(tm('messages.loadError'));
  } finally {
    loadingUmos.value = false;
  }
}

async function refreshData() {
  await loadData();
  showSuccess(tm('messages.refreshSuccess'));
}

async function openAddRuleDialog() {
  addRuleDialog.value = true;
  selectedNewUmo.value = null;
  selectedNewSenderId.value = '';
  if (!isSenderTarget.value) {
    await loadUmos();
  }
}

function buildSenderItem(
  senderId: string,
  rules: SessionRuleSet = {},
): SessionRuleItem {
  return {
    umo: '',
    sender_id: senderId,
    target_type: 'sender',
    platform: '',
    message_type: '',
    session_id: '',
    auto_name: '',
    user_alias: '',
    display_name: senderId,
    rules,
  };
}

function createNewRule() {
  if (isSenderTarget.value) {
    const senderId = selectedNewSenderId.value.trim();
    if (!isSenderSubjectId(senderId)) {
      return;
    }
    addRuleDialog.value = false;
    openRuleEditor(buildSenderItem(senderId));
    return;
  }
  if (!selectedNewUmo.value) {
    return;
  }

  const newItem = buildUmoItem(selectedNewUmo.value);
  addRuleDialog.value = false;
  openRuleEditor(newItem);
}

function openRuleEditor(item: SessionRuleItem) {
  selectedUmo.value = item;
  editingRules.value = item.rules || {};

  const svcConfig = editingRules.value.session_service_config || {};
  const serviceFallback = unwrittenServiceEnabled(item.umo);
  serviceConfig.session_enabled = normalizeBoolean(
    svcConfig.session_enabled,
    serviceFallback,
  );
  serviceConfig.llm_enabled = normalizeBoolean(
    svcConfig.llm_enabled,
    serviceFallback,
  );
  serviceConfig.tts_enabled = normalizeBoolean(
    svcConfig.tts_enabled,
    serviceFallback,
  );
  serviceConfig.session_blocked = svcConfig.session_blocked === true;
  serviceConfig.custom_name = sessionAliasName(item);
  serviceConfig.prompt_id = svcConfig.prompt_id || null;
  senderOverlay.blocked = svcConfig.blocked === true;
  senderOverlay.llm_enabled =
    typeof svcConfig.llm_enabled === 'boolean' ? svcConfig.llm_enabled : null;

  providerConfig.chat_completion =
    editingRules.value.provider_perf_chat_completion || FOLLOW_CONFIG_VALUE;
  providerConfig.speech_to_text =
    editingRules.value.provider_perf_speech_to_text || FOLLOW_CONFIG_VALUE;
  providerConfig.text_to_speech =
    editingRules.value.provider_perf_text_to_speech || FOLLOW_CONFIG_VALUE;

  const pluginRules = editingRules.value.session_plugin_config || {};
  pluginConfig.enabled_plugins = pluginRules.enabled_plugins || [];
  pluginConfig.disabled_plugins = pluginRules.disabled_plugins || [];

  const kbRules = editingRules.value.kb_config || {};
  kbConfig.kb_ids = kbRules.kb_ids || [];
  kbConfig.top_k = kbRules.top_k ?? 5;
  kbConfig.enable_rerank = kbRules.enable_rerank !== false;

  ruleDialog.value = true;
}

function closeRuleEditor() {
  ruleDialog.value = false;
  selectedUmo.value = null;
  editingRules.value = {};
}

async function saveSenderOverlay(
  item: SessionRuleItem & { sender_id: string },
) {
  if (!isSenderSubjectId(item.sender_id)) {
    showError(tm('addRule.senderIdError'));
    return;
  }

  const stored = editingRules.value.session_service_config || {};
  const config: Record<string, boolean | null> = {};
  if (senderOverlay.blocked) {
    config.blocked = true;
  } else if (stored.blocked === true) {
    config.blocked = null;
  }
  if (senderOverlay.llm_enabled !== null) {
    config.llm_enabled = senderOverlay.llm_enabled;
  } else if (typeof stored.llm_enabled === 'boolean') {
    config.llm_enabled = null;
  }

  if (Object.keys(config).length === 0) {
    showSuccess(tm('messages.noChanges'));
    return;
  }

  saving.value = true;
  try {
    const response = await sessionApi.upsertRule({
      target_type: 'sender',
      sender_id: item.sender_id,
      rule_key: 'session_service_config',
      rule_value: config,
    });
    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }
    const savedId =
      normalizeString(
        (response.data.data as { sender_id?: unknown } | undefined)?.sender_id,
      ) || item.sender_id;
    const storedConfig: SessionServiceConfig = {};
    if (typeof config.blocked === 'boolean') {
      storedConfig.blocked = config.blocked;
    }
    if (typeof config.llm_enabled === 'boolean') {
      storedConfig.llm_enabled = config.llm_enabled;
    }
    editingRules.value.session_service_config = storedConfig;
    const existing = rulesList.value.find((row) => row.sender_id === savedId);
    if (existing) {
      existing.rules = { session_service_config: storedConfig };
    } else {
      rulesList.value.push(
        buildSenderItem(savedId, { session_service_config: storedConfig }),
      );
    }
    selectedUmo.value = {
      ...item,
      sender_id: savedId,
      rules: { session_service_config: storedConfig },
    };
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function saveServiceConfig() {
  if (!selectedUmo.value) {
    return;
  }

  if (isSenderRule(selectedUmo.value)) {
    await saveSenderOverlay(selectedUmo.value);
    return;
  }

  saving.value = true;
  try {
    const config: SessionServiceConfig = {
      session_enabled: serviceConfig.session_enabled,
      llm_enabled: serviceConfig.llm_enabled,
      tts_enabled: serviceConfig.tts_enabled,
      session_blocked: serviceConfig.session_blocked,
      custom_name: serviceConfig.custom_name,
    };
    if (serviceConfig.prompt_id !== null) {
      config.prompt_id = serviceConfig.prompt_id;
    }

    const response = await sessionApi.upsertRule({
      umo: selectedUmo.value.umo,
      rule_key: 'session_service_config',
      rule_value: config,
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    const stored = { ...config };
    delete stored.custom_name;
    editingRules.value.session_service_config = stored;
    const item = ensureRuleItem(selectedUmo.value.umo);
    item.user_alias = serviceConfig.custom_name;
    item.rules = { ...item.rules, session_service_config: stored };
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function saveProviderConfig() {
  if (!selectedUmo.value) {
    return;
  }

  saving.value = true;
  try {
    const updateTasks: Promise<unknown>[] = [];
    const deleteTasks: Promise<unknown>[] = [];
    const providerTypes: ProviderRuleType[] = [
      'chat_completion',
      'speech_to_text',
      'text_to_speech',
    ];

    providerTypes.forEach((type) => {
      const value = providerConfig[type];
      const ruleKey = `provider_perf_${type}` as RuleKey;

      if (value && value !== FOLLOW_CONFIG_VALUE) {
        updateTasks.push(
          sessionApi.upsertRule({
            umo: selectedUmo.value!.umo,
            rule_key: ruleKey,
            rule_value: toRuleValue(value),
          }),
        );
      } else if (getProviderRule(editingRules.value, type)) {
        deleteTasks.push(
          sessionApi.deleteRules({
            umo: selectedUmo.value!.umo,
            rule_key: ruleKey,
          }),
        );
      }
    });

    const allTasks = [...updateTasks, ...deleteTasks];
    if (allTasks.length === 0) {
      showSuccess(tm('messages.noChanges'));
      return;
    }

    await Promise.all(allTasks);
    const item = ensureRuleItem(selectedUmo.value.umo);
    providerTypes.forEach((type) => {
      const value = providerConfig[type];
      if (value && value !== FOLLOW_CONFIG_VALUE) {
        setProviderRule(item.rules, type, value);
        setProviderRule(editingRules.value, type, value);
      } else {
        clearProviderRule(item.rules, type);
        clearProviderRule(editingRules.value, type);
      }
    });
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function savePluginConfig() {
  if (!selectedUmo.value) {
    return;
  }

  saving.value = true;
  try {
    const config = {
      enabled_plugins: [...pluginConfig.enabled_plugins],
      disabled_plugins: [...pluginConfig.disabled_plugins],
    };

    if (
      config.enabled_plugins.length === 0 &&
      config.disabled_plugins.length === 0
    ) {
      if (editingRules.value.session_plugin_config) {
        await sessionApi.deleteRules({
          umo: selectedUmo.value.umo,
          rule_key: 'session_plugin_config',
        });
        delete editingRules.value.session_plugin_config;
        const item = findRuleItem(selectedUmo.value.umo);
        if (item) {
          delete item.rules.session_plugin_config;
        }
      }
      showSuccess(tm('messages.saveSuccess'));
      return;
    }

    const response = await sessionApi.upsertRule({
      umo: selectedUmo.value.umo,
      rule_key: 'session_plugin_config',
      rule_value: toRuleValue(config),
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    editingRules.value.session_plugin_config = config;
    const item = ensureRuleItem(selectedUmo.value.umo);
    item.rules.session_plugin_config = config;
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function saveKbConfig() {
  if (!selectedUmo.value) {
    return;
  }

  saving.value = true;
  try {
    const config = {
      kb_ids: [...kbConfig.kb_ids],
      top_k: kbConfig.top_k,
      enable_rerank: kbConfig.enable_rerank,
    };

    if (config.kb_ids.length === 0) {
      if (editingRules.value.kb_config) {
        await sessionApi.deleteRules({
          umo: selectedUmo.value.umo,
          rule_key: 'kb_config',
        });
        delete editingRules.value.kb_config;
        const item = findRuleItem(selectedUmo.value.umo);
        if (item) {
          delete item.rules.kb_config;
        }
      }
      showSuccess(tm('messages.saveSuccess'));
      return;
    }

    const response = await sessionApi.upsertRule({
      umo: selectedUmo.value.umo,
      rule_key: 'kb_config',
      rule_value: toRuleValue(config),
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    editingRules.value.kb_config = config;
    const item = ensureRuleItem(selectedUmo.value.umo);
    item.rules.kb_config = config;
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

function confirmDeleteRules(item: SessionRuleItem) {
  deleteTarget.value = item;
  deleteDialog.value = true;
}

async function deleteAllRules() {
  if (!deleteTarget.value) {
    return;
  }

  deleting.value = true;
  try {
    const response = await sessionApi.deleteRules(
      isSenderRule(deleteTarget.value)
        ? {
            target_type: 'sender',
            sender_id: deleteTarget.value.sender_id,
          }
        : {
            umo: deleteTarget.value.umo,
          },
    );

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.deleteError'));
      return;
    }

    const index = rulesList.value.findIndex((item) =>
      isSenderRule(deleteTarget.value)
        ? item.sender_id === deleteTarget.value.sender_id
        : item.umo === deleteTarget.value!.umo,
    );
    if (index > -1) {
      rulesList.value.splice(index, 1);
    }

    deleteDialog.value = false;
    deleteTarget.value = null;
    await loadData();
    showSuccess(tm('messages.deleteSuccess'));
  } catch {
    showError(tm('messages.deleteError'));
  } finally {
    deleting.value = false;
  }
}

function confirmBatchDelete() {
  if (selectedItems.value.length === 0) {
    return;
  }
  batchDeleteDialog.value = true;
}

async function batchDeleteRules() {
  if (selectedItems.value.length === 0) {
    return;
  }

  deleting.value = true;
  try {
    const response = await sessionApi.deleteRules(
      isSenderTarget.value
        ? {
            target_type: 'sender',
            sender_ids: selectedItems.value
              .map((item) => item.sender_id)
              .filter((id): id is string => Boolean(id)),
          }
        : {
            umos: selectedItems.value.map((item) => item.umo),
          },
    );

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.batchDeleteError'));
      return;
    }

    const data = response.data.data;
    const message =
      typeof data.message === 'string'
        ? data.message
        : tm('messages.batchDeleteSuccess');
    batchDeleteDialog.value = false;
    selectedItems.value = [];
    await loadData();
    showSuccess(message);
  } catch {
    showError(tm('messages.batchDeleteError'));
  } finally {
    deleting.value = false;
  }
}

function showSuccess(message: string) {
  snackbarText.value = message;
  snackbarColor.value = 'success';
  snackbar.value = true;
}

function showError(message: string) {
  snackbarText.value = message;
  snackbarColor.value = 'error';
  snackbar.value = true;
}

function openQuickEditName(item: SessionRuleItem) {
  quickEditNameTarget.value = item;
  quickEditNameValue.value = sessionAliasName(item);
  quickEditNameDialog.value = true;
}

async function saveQuickEditName() {
  if (!quickEditNameTarget.value) {
    return;
  }

  saving.value = true;
  try {
    const existingConfig =
      quickEditNameTarget.value.rules?.session_service_config || {};
    const serviceFallback = unwrittenServiceEnabled(
      quickEditNameTarget.value.umo,
    );
    const config: SessionServiceConfig = {
      ...existingConfig,
      session_enabled: normalizeBoolean(
        existingConfig.session_enabled,
        serviceFallback,
      ),
      llm_enabled: normalizeBoolean(
        existingConfig.llm_enabled,
        serviceFallback,
      ),
      tts_enabled: normalizeBoolean(
        existingConfig.tts_enabled,
        serviceFallback,
      ),
      session_blocked: existingConfig.session_blocked === true,
      custom_name: quickEditNameValue.value,
    };

    const response = await sessionApi.upsertRule({
      umo: quickEditNameTarget.value.umo,
      rule_key: 'session_service_config',
      rule_value: config,
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    const stored = { ...config };
    delete stored.custom_name;
    const item = ensureRuleItem(quickEditNameTarget.value.umo);
    item.user_alias = quickEditNameValue.value;
    item.rules.session_service_config = stored;
    quickEditNameDialog.value = false;
    quickEditNameTarget.value = null;
    quickEditNameValue.value = '';
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

function collectProviderTask(
  targetPayload: ReturnType<typeof buildBatchTargetPayload>,
  providerValue: string,
  providerType: 'chat_completion' | 'text_to_speech',
  ruleKey: string,
): Promise<unknown> {
  if (providerValue === FOLLOW_CONFIG_VALUE) {
    return sessionApi.deleteRules({ ...targetPayload, rule_key: ruleKey });
  }
  const providerData: BatchSessionProviderRequest = {
    ...targetPayload,
    provider_type: providerType,
    provider_id: providerValue,
  };
  return sessionApi.batchUpdateProvider(providerData);
}

function isOkResult(result: unknown): boolean {
  if (!result || typeof result !== 'object') {
    return false;
  }
  const responseData = (result as { data?: { status?: string } }).data;
  return responseData?.status === 'ok';
}

async function applyBatchChanges() {
  batchUpdating.value = true;
  try {
    let scope = batchScope.value;
    let groupId: string | null = null;
    let umos: string[] = [];

    if (scope.startsWith('custom_group:')) {
      groupId = scope.split(':')[1] || null;
      scope = 'custom_group';
    }

    if (scope === 'selected') {
      umos = selectedItems.value.map((item) => item.umo);
      if (umos.length === 0) {
        showError(tm('messages.selectSessionsFirst'));
        return;
      }
    }

    const targetPayload = buildBatchTargetPayload(scope, groupId, umos);
    const tasks: Promise<unknown>[] = [];

    if (batchLlmStatus.value !== null || batchTtsStatus.value !== null) {
      const serviceData: BatchSessionServiceRequest = { ...targetPayload };
      if (batchLlmStatus.value !== null) {
        serviceData.llm_enabled = batchLlmStatus.value;
      }
      if (batchTtsStatus.value !== null) {
        serviceData.tts_enabled = batchTtsStatus.value;
      }
      tasks.push(sessionApi.batchUpdateService(serviceData));
    }

    if (batchChatProvider.value !== null) {
      tasks.push(
        collectProviderTask(
          targetPayload,
          batchChatProvider.value,
          'chat_completion',
          'provider_perf_chat_completion',
        ),
      );
    }

    if (batchTtsProvider.value !== null) {
      tasks.push(
        collectProviderTask(
          targetPayload,
          batchTtsProvider.value,
          'text_to_speech',
          'provider_perf_text_to_speech',
        ),
      );
    }

    if (tasks.length === 0) {
      showError(tm('messages.selectAtLeastOneConfig'));
      return;
    }

    const results = await Promise.all(tasks);
    const allOk = results.every(isOkResult);

    if (!allOk) {
      showError(tm('messages.partialUpdateFailed'));
      return;
    }

    batchLlmStatus.value = null;
    batchTtsStatus.value = null;
    batchChatProvider.value = null;
    batchTtsProvider.value = null;
    await loadData();
    showSuccess(tm('messages.batchUpdateSuccess'));
  } catch {
    showError(tm('messages.batchUpdateError'));
  } finally {
    batchUpdating.value = false;
  }
}

async function loadGroups() {
  groupsLoading.value = true;
  try {
    const response = await sessionApi.listGroups();
    if (response.data.status !== 'ok') {
      return;
    }

    const groupsValue = response.data.data.groups;
    const rawGroups: unknown[] = Array.isArray(groupsValue) ? groupsValue : [];

    groups.value = rawGroups
      .map((group) => normalizeGroup(group))
      .filter((group): group is GroupItem => group !== null);
  } catch (error) {
    console.error('加载分组失败:', error);
  } finally {
    groupsLoading.value = false;
  }
}

async function loadAvailableUmos() {
  if (availableUmos.value.length > 0) {
    return;
  }

  loadingUmos.value = true;
  try {
    const response = await sessionApi.activeUmos();
    if (response.data.status !== 'ok') {
      return;
    }

    mergeUmoInfos(response.data.data.umo_infos);
    availableUmos.value = normalizeStringArray(response.data.data.umos);
  } catch (error) {
    console.error('加载会话列表失败:', error);
  } finally {
    loadingUmos.value = false;
  }
}

function openCreateGroupDialog() {
  groupDialogMode.value = 'create';
  resetGroupEditor();
  groupDialog.value = true;
}

function openEditGroupDialog(group: GroupItem) {
  groupDialogMode.value = 'edit';
  editingGroup.id = group.id;
  editingGroup.name = group.name;
  editingGroup.umos = [...group.umos];
  groupMemberSearch.value = '';
  groupSelectedSearch.value = '';
  groupDialog.value = true;
}

function addToGroup(umo: string) {
  if (!editingGroup.umos.includes(umo)) {
    editingGroup.umos.push(umo);
  }
}

function removeFromGroup(umo: string) {
  const index = editingGroup.umos.indexOf(umo);
  if (index > -1) {
    editingGroup.umos.splice(index, 1);
  }
}

function addAllToGroup() {
  unselectedUmos.value.forEach((umo) => {
    if (!editingGroup.umos.includes(umo)) {
      editingGroup.umos.push(umo);
    }
  });
}

function removeAllFromGroup() {
  editingGroup.umos = [];
}

async function saveGroup() {
  if (!editingGroup.name.trim()) {
    showError(tm('messages.groupNameRequired'));
    return;
  }

  try {
    const payload = {
      name: editingGroup.name,
      umos: editingGroup.umos,
    };

    const response =
      groupDialogMode.value === 'create'
        ? await sessionApi.createGroup(payload)
        : await sessionApi.updateGroup(editingGroup.id || '', payload);

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveGroupError'));
      return;
    }

    const data =
      response.data.data && typeof response.data.data === 'object'
        ? (response.data.data as Record<string, unknown>)
        : {};
    const message =
      typeof data.message === 'string'
        ? data.message
        : tm('messages.saveSuccess');

    groupDialog.value = false;
    await loadGroups();
    showSuccess(message);
  } catch {
    showError(tm('messages.saveGroupError'));
  }
}

async function deleteGroup(group: GroupItem) {
  const message = tm('groups.deleteConfirm', { name: group.name });
  if (!(await askForConfirmationDialog(message, confirmDialog))) {
    return;
  }

  try {
    const response = await sessionApi.deleteGroup(group.id);
    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.deleteGroupError'));
      return;
    }

    const data =
      response.data.data && typeof response.data.data === 'object'
        ? (response.data.data as Record<string, unknown>)
        : {};
    const successMessage =
      typeof data.message === 'string'
        ? data.message
        : tm('messages.deleteSuccess');

    await loadGroups();
    showSuccess(successMessage);
  } catch {
    showError(tm('messages.deleteGroupError'));
  }
}

async function addSelectedToGroup(groupId: string) {
  if (selectedItems.value.length === 0) {
    showError(tm('messages.selectSessionsToAddFirst'));
    return;
  }

  try {
    const response = await sessionApi.updateGroup(groupId, {
      add_umos: selectedItems.value.map((item) => item.umo),
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.addToGroupError'));
      return;
    }

    await loadGroups();
    showSuccess(
      tm('messages.addToGroupSuccess', {
        count: selectedItems.value.length,
      }),
    );
  } catch {
    showError(tm('messages.addToGroupError'));
  }
}
</script>

<style scoped>
.session-management-page {
  min-width: 0;
}

.session-rules-toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--astrbot-space-3);
  padding: var(--astrbot-space-3) var(--astrbot-space-4);
}

.session-rules-toolbar__search {
  flex: 1 1 220px;
  min-width: 0;
}

.session-rules-toolbar__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--astrbot-space-2);
}

@media (max-width: 600px) {
  .session-rules-scroll-hint {
    display: none;
  }

  .session-rules-toolbar__search,
  .session-rules-toolbar__actions {
    flex-basis: 100%;
  }

  .session-rules-toolbar__actions {
    justify-content: flex-end;
  }

  .session-rules-toolbar__actions :deep(.v-btn) {
    min-height: var(--astrbot-control-size);
  }
}
</style>

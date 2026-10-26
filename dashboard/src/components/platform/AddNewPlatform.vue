<template>
  <v-dialog
    v-model="showDialog"
    max-width="800px"
    max-height="90%"
    scrollable
    :aria-label="
      updatingMode
        ? `${tm('dialog.edit')} ${updatingPlatformConfig.id} ${tm(
            'dialog.adapter',
          )}`
        : tm('dialog.addPlatform')
    "
    @after-enter="prepareData"
  >
    <v-card
      class="app-dialog platform-dialog__card"
      :title="
        updatingMode
          ? `${tm('dialog.edit')} ${updatingPlatformConfig.id} ${tm(
              'dialog.adapter',
            )}`
          : tm('dialog.addPlatform')
      "
    >
      <v-card-text
        ref="dialogScrollContainer"
        class="pa-4 ml-2 platform-dialog__content"
      >
        <PlatformCreationSection
          :updating-mode="updatingMode"
          :platform-templates="platformTemplates"
          :selected-platform-type="selectedPlatformType"
          :selected-platform-config="selectedPlatformConfig"
          :lark-creation-mode="larkCreationMode"
          :dingtalk-creation-mode="dingtalkCreationMode"
          :qq-official-creation-mode="qqOfficialCreationMode"
          :is-lark-platform="isLarkPlatform"
          :is-dingtalk-platform="isDingtalkPlatform"
          :is-qq-official-platform="isQqOfficialPlatform"
          :is-weixin-oc-platform="isWeixinOcPlatform"
          :scan-platform-id-error="scanPlatformIdError"
          :updating-platform-config="updatingPlatformConfig"
          :platform-metadata="platformMetadata"
          @update:selected-platform-type="selectedPlatformType = $event"
          @update:lark-creation-mode="larkCreationMode = $event"
          @update:dingtalk-creation-mode="dingtalkCreationMode = $event"
          @update:qq-official-creation-mode="qqOfficialCreationMode = $event"
          @update:scan-platform-id="setScanPlatformId"
          @platform-registration-created="handlePlatformRegistrationCreated"
          @show-toast="handleShowToast"
        />

        <div class="platform-dialog__step mt-6">
          <div>
            <v-icon icon="mdi-numeric-2-circle" class="mr-3"></v-icon>
          </div>
          <div class="platform-dialog__step-content">
            <div class="d-flex align-center justify-space-between">
              <div>
                <div class="d-flex align-center">
                  <h3>
                    {{ tm('createDialog.configFileTitle') }}
                  </h3>
                  <v-chip
                    v-if="!updatingMode"
                    size="x-small"
                    color="primary"
                    variant="tonal"
                    rounded="sm"
                    class="ml-2"
                    >{{ tm('createDialog.optional') }}</v-chip
                  >
                </div>
                <small class="text-medium-emphasis">{{
                  tm('createDialog.configHint')
                }}</small>
                <small v-if="!updatingMode" class="text-medium-emphasis">{{
                  tm('createDialog.configDefaultHint')
                }}</small>
              </div>
              <div>
                <v-btn
                  variant="plain"
                  icon
                  class="mt-2"
                  @click="toggleConfigSection"
                >
                  <v-icon>{{
                    showConfigSection ? 'mdi-chevron-up' : 'mdi-chevron-down'
                  }}</v-icon>
                </v-btn>
              </div>
            </div>

            <div v-if="showConfigSection">
              <div v-if="!updatingMode">
                <v-radio-group
                  v-model="aBConfigRadioVal"
                  class="mt-2"
                  :aria-label="tm('createDialog.configFileTitle')"
                  hide-details
                >
                  <v-radio value="0">
                    <template #label>
                      <span>{{ tm('createDialog.useExistingConfig') }}</span>
                    </template>
                  </v-radio>
                  <div
                    v-if="aBConfigRadioVal === '0'"
                    class="d-flex align-center ml-10 my-2"
                  >
                    <v-select
                      v-model="selectedAbConfId"
                      :items="configInfoList"
                      item-title="name"
                      item-value="id"
                      :label="tm('createDialog.selectConfigLabel')"
                      variant="outlined"
                      rounded="md"
                      density="comfortable"
                      hide-details
                      class="platform-config-select"
                    >
                    </v-select>
                    <v-btn
                      icon
                      variant="text"
                      density="comfortable"
                      class="ml-2"
                      :disabled="!selectedAbConfId"
                      @click="openConfigDrawer(selectedAbConfId)"
                    >
                      <v-icon>mdi-arrow-top-right-thick</v-icon>
                    </v-btn>
                  </div>
                  <v-radio
                    value="1"
                    :label="tm('createDialog.createNewConfig')"
                  >
                  </v-radio>
                  <div
                    v-if="aBConfigRadioVal === '1'"
                    class="d-flex align-center"
                  >
                    <v-text-field
                      v-model="selectedAbConfId"
                      :label="tm('createDialog.newConfigNameLabel')"
                      variant="outlined"
                      rounded="md"
                      density="comfortable"
                      hide-details
                      class="ml-10 my-2 platform-config-select"
                    >
                    </v-text-field>
                  </div>
                </v-radio-group>

                <!-- 新配置文件编辑区域 -->
                <div v-if="aBConfigRadioVal === '1'" class="mt-4">
                  <div
                    v-if="newConfigLoading"
                    class="d-flex justify-center py-4"
                  >
                    <v-progress-circular
                      indeterminate
                      color="primary"
                    ></v-progress-circular>
                  </div>
                  <div
                    v-else-if="newConfigData && newConfigMetadata"
                    class="config-preview-container"
                  >
                    <h4 class="mb-3">
                      {{ tm('createDialog.newConfigTitle') }}
                    </h4>
                    <AstrBotCoreConfigWrapper
                      :metadata="newConfigMetadata"
                      :config-data="newConfigData"
                    />
                  </div>
                  <div v-else class="text-center py-4 text-medium-emphasis">
                    <v-icon>mdi-information-outline</v-icon>
                    <p class="mt-2">
                      {{ tm('createDialog.newConfigLoadFailed') }}
                    </p>
                  </div>
                </div>
              </div>

              <PlatformRouteRulesEditor
                v-else
                :platform-routes="platformRoutes"
                :is-editing-routes="isEditingRoutes"
                :updating-mode="updatingMode"
                :known-route-umo-items="filteredKnownRouteUmoItems"
                :loading-known-route-umos="loadingKnownRouteUmos"
                :known-route-umo-info-map="knownRouteUmoInfoMap"
                :config-info-list="configInfoList"
                @update:platform-routes="platformRoutes = $event"
                @add-route="addNewRoute"
                @move-route-up="moveRouteUp"
                @move-route-down="moveRouteDown"
                @delete-route="deleteRoute"
                @toggle-edit-mode="toggleEditMode"
                @toggle-route-source-mode="toggleRouteSourceMode"
                @apply-known-route-source="applyKnownRouteSource"
                @load-known-route-umos="loadKnownRouteUmos"
                @open-config-drawer="openConfigDrawer"
              />
            </div>
          </div>
        </div>
      </v-card-text>

      <v-card-actions class="platform-dialog__actions">
        <v-spacer></v-spacer>
        <v-btn text @click="closeDialog">{{ tm('dialog.cancel') }}</v-btn>
        <v-btn
          v-if="!updatingMode"
          :disabled="!canSave"
          color="primary"
          :loading="loading"
          @click="newPlatform"
          >{{ tm('dialog.save') }}</v-btn
        >
        <v-btn
          v-else
          :disabled="!selectedAbConfId"
          color="primary"
          :loading="loading"
          @click="newPlatform"
          >{{ tm('dialog.save') }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>

  <PlatformIdConflictDialog
    v-model="showIdConflictDialog"
    :conflict-id="conflictId"
    @confirm="handleIdConflictConfirm(false)"
  />

  <PlatformSecurityWarningDialog
    v-model="showOneBotEmptyTokenWarnDialog"
    :message-key="oneBotTokenWarningMessageKey"
    :tutorial-link="oneBotTokenWarningTutorialLink"
    @confirm="handleOneBotEmptyTokenWarningDismiss(true)"
    @dismiss="handleOneBotEmptyTokenWarningDismiss(false)"
  />

  <ConfigProfileDrawer
    v-model="showConfigDrawer"
    :config-id="configDrawerTargetId || 'default'"
  />
</template>

<script setup lang="ts">
import { botApi, configProfileApi, configRouteApi, sessionApi } from '@/api/v1';
import { computed, nextTick, reactive, ref, toRefs, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { getTutorialLink } from '@/utils/platformUtils';
import { resolveErrorMessage } from '@/utils/errorUtils';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import ConfigProfileDrawer from '@/components/config/ConfigProfileDrawer.vue';
import PlatformCreationSection from '@/components/platform/PlatformCreationSection.vue';
import PlatformIdConflictDialog from '@/components/platform/PlatformIdConflictDialog.vue';
import PlatformRouteRulesEditor from '@/components/platform/PlatformRouteRulesEditor.vue';
import PlatformSecurityWarningDialog from '@/components/platform/PlatformSecurityWarningDialog.vue';
import {
  asRecord,
  buildRandomPlatformIdSuffix,
  deepClone,
  getOneBotSecurityToken,
  getRouteSourceMode,
  getString,
  isParsedUmopMatchPlatform,
  isPlatformIdValid,
  isUmopMatchPlatform,
  normalizeConfigInfoList,
  normalizeKnownRouteUmoInfos,
  normalizePlatformConfigList,
  normalizePlatformTemplates,
  normalizeRoutingTable,
  normalizeStringArray,
  parseUmop,
  sanitizePlatformIdPart,
  type ConfigInfo,
  type ConfigMode,
  type CreationMode,
  type KnownRouteUmoInfo,
  type PlatformConfigItem,
  type PlatformRoute,
  type RecordValue,
  type RegistrationCreatedPayload,
  type ToastPayload,
} from '@/components/platform/platformConfigHelpers';
import {
  runBotMutationWithStepUp,
  runConfigMutationWithStepUp,
  stepUpHeaders,
  type RequestDashboardStepUp,
} from '@/utils/stepUp';

defineOptions({
  name: 'AddNewPlatform',
});

interface PlatformMetadataState extends RecordValue {
  platform_group?: {
    metadata?: RecordValue & {
      platform?: {
        config_template?: Record<string, PlatformConfigItem>;
      };
    };
  };
}

interface PlatformConfigState extends RecordValue {
  platform?: unknown[];
}

interface ComponentState {
  selectedPlatformType: string | null;
  selectedPlatformConfig: PlatformConfigItem | null;
  larkCreationMode: CreationMode;
  dingtalkCreationMode: CreationMode;
  qqOfficialCreationMode: CreationMode;
  aBConfigRadioVal: ConfigMode;
  selectedAbConfId: string | null;
  configInfoList: ConfigInfo[];
  newConfigData: RecordValue | null;
  newConfigMetadata: RecordValue | null;
  newConfigLoading: boolean;
  platformRoutes: PlatformRoute[];
  platformRoutesLoaded: boolean;
  isEditingRoutes: boolean;
  knownRouteUmos: string[];
  knownRouteUmoInfoMap: Record<string, KnownRouteUmoInfo>;
  loadingKnownRouteUmos: boolean;
  showIdConflictDialog: boolean;
  conflictId: string;
  idConflictResolve: ((value: boolean) => void) | null;
  showOneBotEmptyTokenWarnDialog: boolean;
  oneBotTokenWarningPlatformType: string | null;
  oneBotEmptyTokenWarningResolve: ((value: boolean) => void) | null;
  scanPlatformIdCustomized: boolean;
  loading: boolean;
  showConfigSection: boolean;
  showConfigDrawer: boolean;
  configDrawerTargetId: string | null;
  originalUpdatingPlatformId: string | null;
}

interface Props {
  show?: boolean;
  metadata?: PlatformMetadataState;
  configData?: PlatformConfigState;
  updatingMode?: boolean;
  updatingPlatformConfig?: PlatformConfigItem;
  requestStepUp?: RequestDashboardStepUp;
}

type DialogScrollTarget = HTMLElement | { $el?: HTMLElement | null } | null;

const props = withDefaults(defineProps<Props>(), {
  show: false,
  metadata: () => ({}),
  configData: () => ({}),
  updatingMode: false,
  updatingPlatformConfig: () => ({}),
  requestStepUp: undefined,
});

const emit = defineEmits<{
  'update:show': [value: boolean];
  'show-toast': [payload: ToastPayload];
  'refresh-config': [platformId?: string];
}>();

const { tm } = useModuleI18n('features/platform');
const { metadata, configData, updatingMode, updatingPlatformConfig } =
  toRefs(props);

const state = reactive<ComponentState>({
  selectedPlatformType: null,
  selectedPlatformConfig: null,
  larkCreationMode: '',
  dingtalkCreationMode: '',
  qqOfficialCreationMode: '',
  aBConfigRadioVal: '0',
  selectedAbConfId: 'default',
  configInfoList: [],
  newConfigData: null,
  newConfigMetadata: null,
  newConfigLoading: false,
  platformRoutes: [],
  platformRoutesLoaded: false,
  isEditingRoutes: false,
  knownRouteUmos: [],
  knownRouteUmoInfoMap: {},
  loadingKnownRouteUmos: false,
  showIdConflictDialog: false,
  conflictId: '',
  idConflictResolve: null,
  showOneBotEmptyTokenWarnDialog: false,
  oneBotTokenWarningPlatformType: null,
  oneBotEmptyTokenWarningResolve: null,
  scanPlatformIdCustomized: false,
  loading: false,
  showConfigSection: false,
  showConfigDrawer: false,
  configDrawerTargetId: null,
  originalUpdatingPlatformId: null,
});

const {
  selectedPlatformType,
  selectedPlatformConfig,
  larkCreationMode,
  dingtalkCreationMode,
  qqOfficialCreationMode,
  aBConfigRadioVal,
  selectedAbConfId,
  configInfoList,
  newConfigData,
  newConfigMetadata,
  newConfigLoading,
  platformRoutes,
  isEditingRoutes,
  knownRouteUmoInfoMap,
  loadingKnownRouteUmos,
  showIdConflictDialog,
  conflictId,
  showOneBotEmptyTokenWarnDialog,
  loading,
  showConfigSection,
  showConfigDrawer,
  configDrawerTargetId,
} = toRefs(state);

const dialogScrollContainer = ref<DialogScrollTarget>(null);
const ONEBOT_TOKEN_WARNING_PLATFORM_TYPES = new Set(['aiocqhttp', 'napcat']);

const showDialog = computed({
  get: () => props.show,
  set: (value: boolean) => void emit('update:show', value),
});

const platformTemplates = computed<Record<string, PlatformConfigItem>>(() =>
  normalizePlatformTemplates(
    metadata.value.platform_group?.metadata?.platform?.config_template,
  ),
);

const platformMetadata = computed<RecordValue>(
  () => metadata.value.platform_group?.metadata ?? {},
);

function isCreationModeReady(
  mode: CreationMode,
  requiredFields: unknown[],
): boolean {
  if (!mode) {
    return false;
  }
  if (mode !== 'scan') {
    return true;
  }
  return requiredFields.every(Boolean);
}

const canSave = computed(() => {
  if (
    !state.selectedPlatformType ||
    !isPlatformIdValid(state.selectedPlatformConfig?.id)
  ) {
    return false;
  }

  if (
    isLarkPlatform.value &&
    !isCreationModeReady(state.larkCreationMode, [
      state.selectedPlatformConfig?.app_id,
      state.selectedPlatformConfig?.app_secret,
    ])
  ) {
    return false;
  }

  if (
    isDingtalkPlatform.value &&
    !isCreationModeReady(state.dingtalkCreationMode, [
      state.selectedPlatformConfig?.client_id,
      state.selectedPlatformConfig?.client_secret,
    ])
  ) {
    return false;
  }

  if (
    isQqOfficialPlatform.value &&
    !isCreationModeReady(state.qqOfficialCreationMode, [
      state.selectedPlatformConfig?.appid,
      state.selectedPlatformConfig?.secret,
    ])
  ) {
    return false;
  }

  if (
    isWeixinOcPlatform.value &&
    !state.selectedPlatformConfig?.weixin_oc_token
  ) {
    return false;
  }

  if (state.aBConfigRadioVal === '0') {
    return Boolean(state.selectedAbConfId);
  }

  if (state.aBConfigRadioVal === '1') {
    return Boolean(state.selectedAbConfId && state.newConfigData);
  }

  return false;
});

const oneBotTokenWarningTutorialLink = computed(() =>
  getTutorialLink(state.oneBotTokenWarningPlatformType ?? 'aiocqhttp'),
);
const oneBotTokenWarningMessageKey = computed(() =>
  state.oneBotTokenWarningPlatformType === 'napcat'
    ? 'dialog.securityWarning.napcatTokenMissing'
    : 'dialog.securityWarning.aiocqhttpTokenMissing',
);

const routePlatformId = computed(() => {
  if (updatingMode.value) {
    return (
      getString(updatingPlatformConfig.value.id) ??
      state.originalUpdatingPlatformId ??
      ''
    );
  }
  return getString(state.selectedPlatformConfig?.id) ?? '';
});

const filteredKnownRouteUmoItems = computed(() => {
  const platformId = routePlatformId.value;
  return state.knownRouteUmos.filter(
    (umo) => parseUmop(umo)?.platform === platformId,
  );
});

const isLarkPlatform = computed(
  () => getString(state.selectedPlatformConfig?.type) === 'lark',
);
const isWeixinOcPlatform = computed(
  () => getString(state.selectedPlatformConfig?.type) === 'weixin_oc',
);
const isDingtalkPlatform = computed(
  () => getString(state.selectedPlatformConfig?.type) === 'dingtalk',
);
const isQqOfficialPlatform = computed(() =>
  ['qq_official', 'qq_official_webhook'].includes(
    getString(state.selectedPlatformConfig?.type) ?? '',
  ),
);
const scanPlatformIdError = computed(() => {
  const platformId = String(state.selectedPlatformConfig?.id || '');
  if (!platformId) {
    return tm('registrationAction.platformIdRequired');
  }
  if (!isPlatformIdValid(platformId)) {
    return tm('registrationAction.platformIdInvalid');
  }
  return '';
});

watch(selectedPlatformType, (newType) => {
  if (newType && platformTemplates.value[newType]) {
    state.selectedPlatformConfig = deepClone(platformTemplates.value[newType]);
  } else {
    state.selectedPlatformConfig = null;
  }
  state.larkCreationMode = '';
  state.dingtalkCreationMode = '';
  state.qqOfficialCreationMode = '';
  state.scanPlatformIdCustomized = false;
});

watch(aBConfigRadioVal, (newValue) => {
  if (newValue === '1') {
    state.selectedAbConfId = null;
    void getDefaultConfigTemplate();
    return;
  }

  state.newConfigData = null;
  state.newConfigMetadata = null;
  if (!state.selectedAbConfId) {
    state.selectedAbConfId = 'default';
  }
});

watch(showIdConflictDialog, (newValue) => {
  if (!newValue && state.idConflictResolve) {
    state.idConflictResolve(false);
    state.idConflictResolve = null;
  }
});

watch(showOneBotEmptyTokenWarnDialog, (newValue) => {
  if (!newValue && state.oneBotEmptyTokenWarningResolve) {
    state.oneBotEmptyTokenWarningResolve(true);
    state.oneBotEmptyTokenWarningResolve = null;
  }
});

watch(
  updatingPlatformConfig,
  (newConfig) => {
    const platformId = getString(newConfig?.id);
    if (updatingMode.value && platformId) {
      state.originalUpdatingPlatformId = platformId;
      void getPlatformConfigs(platformId);
    }
  },
  { immediate: true },
);

watch(showConfigSection, async (newValue) => {
  if (newValue) {
    await nextTick();
    scrollDialogToBottom();
  }
});

watch(
  updatingMode,
  (newValue) => {
    if (newValue) {
      state.showConfigSection = true;
      state.isEditingRoutes = false;
    }
  },
  { immediate: true },
);

function resetForm() {
  state.selectedPlatformType = null;
  state.selectedPlatformConfig = null;
  state.larkCreationMode = '';
  state.dingtalkCreationMode = '';
  state.qqOfficialCreationMode = '';
  state.scanPlatformIdCustomized = false;
  state.aBConfigRadioVal = '0';
  state.selectedAbConfId = 'default';
  state.newConfigData = null;
  state.newConfigMetadata = null;
  state.newConfigLoading = false;
  state.showConfigSection = false;
  state.isEditingRoutes = false;
  state.knownRouteUmos = [];
  state.knownRouteUmoInfoMap = {};
  state.loadingKnownRouteUmos = false;
  state.showConfigDrawer = false;
  state.configDrawerTargetId = null;
  state.originalUpdatingPlatformId = null;
}

function closeDialog() {
  resetForm();
  showDialog.value = false;
}

async function getConfigInfoList() {
  const res = await configProfileApi.list();
  state.configInfoList = normalizeConfigInfoList(res.data.data.info_list);
}

async function getDefaultConfigTemplate() {
  state.newConfigLoading = true;
  try {
    const response = await configProfileApi.schema();
    state.newConfigData = asRecord(response.data.data.config);
    state.newConfigMetadata = asRecord(response.data.data.metadata);
  } catch (error) {
    console.error('获取默认配置模板失败:', error);
    state.newConfigData = null;
    state.newConfigMetadata = null;
  } finally {
    state.newConfigLoading = false;
  }
}

function openConfigDrawer(configId: string | null | undefined) {
  const targetId = configId || 'default';
  if (
    configId &&
    state.configInfoList.findIndex((config) => config.id === configId) === -1
  ) {
    showError(tm('messages.configNotFoundOpenConfig'));
  }
  state.configDrawerTargetId = targetId;
  state.showConfigDrawer = true;
}

async function newPlatform() {
  state.loading = true;
  if (updatingMode.value) {
    const platformType = getString(updatingPlatformConfig.value.type);
    const token = getOneBotSecurityToken(updatingPlatformConfig.value)?.trim();
    if (
      platformType &&
      ONEBOT_TOKEN_WARNING_PLATFORM_TYPES.has(platformType) &&
      !token
    ) {
      const continueWithWarning =
        await showOneBotEmptyTokenWarning(platformType);
      if (!continueWithWarning) {
        state.loading = false;
        return;
      }
    }
    await updatePlatform();
    return;
  }

  await savePlatform();
}

async function updatePlatform() {
  if (!state.platformRoutesLoaded) {
    state.loading = false;
    showError(tm('messages.routingLoadRequired'));
    return;
  }

  const platformId =
    state.originalUpdatingPlatformId ??
    getString(updatingPlatformConfig.value.id);
  if (!platformId) {
    state.loading = false;
    showError(tm('messages.updateMissingPlatformId'));
    return;
  }

  if (!isPlatformIdValid(platformId)) {
    state.loading = false;
    showError(tm('dialog.invalidPlatformId'));
    return;
  }

  try {
    const resp = await runBotMutationWithStepUp(
      (stepUp) =>
        stepUp
          ? botApi.update(platformId, updatingPlatformConfig.value, stepUp)
          : botApi.update(platformId, updatingPlatformConfig.value),
      platformId,
      props.requestStepUp,
    );
    if (!resp) {
      state.loading = false;
      return;
    }
    if (resp.data.status === 'error') {
      throw new Error(resp.data.message || tm('messages.platformUpdateFailed'));
    }

    await saveRoutesInternal();
    state.loading = false;
    showDialog.value = false;
    resetForm();
    emit('refresh-config');
    showSuccess(tm('messages.updateSuccess'));
  } catch (error) {
    state.loading = false;
    showError(resolveErrorMessage(error, tm('messages.platformUpdateFailed')));
  }
}

async function savePlatform() {
  const platformConfig = state.selectedPlatformConfig;
  const platformId = getString(platformConfig?.id);
  const platformType = getString(platformConfig?.type);
  if (!platformConfig || !platformId || !isPlatformIdValid(platformId)) {
    state.loading = false;
    showError(tm('dialog.invalidPlatformId'));
    return;
  }

  const existingPlatform = normalizePlatformConfigList(
    configData.value.platform,
  ).find((platform) => platform.id === platformId);
  if (existingPlatform || platformId === 'webchat') {
    const confirmed = await confirmIdConflict(platformId);
    if (!confirmed) {
      state.loading = false;
      return;
    }
  }

  if (platformType && ONEBOT_TOKEN_WARNING_PLATFORM_TYPES.has(platformType)) {
    const token = getOneBotSecurityToken(platformConfig)?.trim();
    if (!token) {
      const continueWithWarning =
        await showOneBotEmptyTokenWarning(platformType);
      if (!continueWithWarning) {
        state.loading = false;
        return;
      }
    }
  }

  try {
    const res = await runBotMutationWithStepUp(
      (stepUp) =>
        stepUp
          ? botApi.create(platformConfig, stepUp)
          : botApi.create(platformConfig),
      'collection',
      props.requestStepUp,
    );
    if (!res) {
      state.loading = false;
      return;
    }
    await handleConfigFile();
    state.loading = false;
    showDialog.value = false;
    resetForm();
    emit('refresh-config', platformId);
    showSuccess(res.data.message || tm('messages.addSuccessWithConfig'));
  } catch (error) {
    state.loading = false;
    showError(resolveErrorMessage(error, tm('messages.addSuccessWithConfig')));
  }
}

async function handleConfigFile() {
  const platformId = getString(state.selectedPlatformConfig?.id);
  if (!state.selectedAbConfId || !platformId) {
    return;
  }

  let configId: string | null = null;
  if (state.aBConfigRadioVal === '0') {
    configId = state.selectedAbConfId;
  } else if (state.aBConfigRadioVal === '1') {
    configId = await createNewConfigFile(state.selectedAbConfId);
  }

  if (!configId) {
    throw new Error(tm('messages.configIdMissing'));
  }

  await updateRoutingTable(`${platformId}:*:*`, configId);
}

async function updateRoutingTable(umop: string, configId: string) {
  try {
    await configRouteApi.upsert(umop, { config_id: configId });
  } catch (error) {
    console.error('更新路由表失败:', error);
    throw new Error(
      tm('messages.routingUpdateFailed', {
        message: resolveErrorMessage(
          error,
          tm('messages.platformUpdateFailed'),
        ),
      }),
    );
  }
}

async function createNewConfigFile(configName: string) {
  try {
    const configPayload =
      state.aBConfigRadioVal === '1' && state.newConfigData
        ? state.newConfigData
        : undefined;

    const createRes = await runConfigMutationWithStepUp(
      (stepUp) =>
        configProfileApi.create(
          {
            name: configName,
            config: configPayload,
          },
          stepUp ? { headers: stepUpHeaders(stepUp) } : undefined,
        ),
      'default',
      props.requestStepUp,
    );
    if (!createRes) {
      throw new Error(tm('messages.configIdMissing'));
    }

    const newConfigId = getString(createRes.data.data.conf_id);
    if (!newConfigId) {
      throw new Error(tm('messages.configIdMissing'));
    }
    return newConfigId;
  } catch (error) {
    console.error('创建新配置文件失败:', error);
    throw new Error(
      tm('messages.createConfigFailed', {
        message: resolveErrorMessage(
          error,
          tm('messages.platformUpdateFailed'),
        ),
      }),
    );
  }
}

function confirmIdConflict(id: string): Promise<boolean> {
  state.conflictId = id;
  state.showIdConflictDialog = true;
  return new Promise((resolve) => {
    state.idConflictResolve = resolve;
  });
}

function handleIdConflictConfirm(confirmed: boolean) {
  if (state.idConflictResolve) {
    state.idConflictResolve(confirmed);
    state.idConflictResolve = null;
  }
  state.showIdConflictDialog = false;
}

function showOneBotEmptyTokenWarning(platformType: string): Promise<boolean> {
  state.oneBotTokenWarningPlatformType = platformType;
  state.showOneBotEmptyTokenWarnDialog = true;
  return new Promise((resolve) => {
    state.oneBotEmptyTokenWarningResolve = resolve;
  });
}

function handleOneBotEmptyTokenWarningDismiss(continueWithWarning: boolean) {
  state.showOneBotEmptyTokenWarnDialog = false;
  if (state.oneBotEmptyTokenWarningResolve) {
    state.oneBotEmptyTokenWarningResolve(continueWithWarning);
    state.oneBotEmptyTokenWarningResolve = null;
  }
  state.oneBotTokenWarningPlatformType = null;

  if (!continueWithWarning) {
    state.loading = false;
  }
}

function showSuccess(message: string) {
  emit('show-toast', { message, type: 'success' });
}

function showError(message: string) {
  emit('show-toast', { message, type: 'error' });
}

function handleShowToast(payload: ToastPayload) {
  emit('show-toast', payload);
}

function setScanPlatformId(value: string | null) {
  if (!state.selectedPlatformConfig) {
    return;
  }
  state.scanPlatformIdCustomized = true;
  state.selectedPlatformConfig.id = String(value || '');
}

function handlePlatformRegistrationCreated(data: RegistrationCreatedPayload) {
  if (!state.selectedPlatformConfig) {
    return;
  }
  if (state.scanPlatformIdCustomized) {
    return;
  }

  const currentId = String(state.selectedPlatformConfig.id || '').trim();
  const platformType = getString(state.selectedPlatformConfig.type);
  if (!currentId || !platformType) {
    return;
  }

  let suffix = '';
  const explicitSuffix = sanitizePlatformIdPart(data.platform_id_suffix);
  if (explicitSuffix) {
    suffix =
      explicitSuffix.startsWith('_') || explicitSuffix.startsWith('-')
        ? explicitSuffix
        : `_${explicitSuffix}`;
  } else if (data.bot_name) {
    const safeBotName = sanitizePlatformIdPart(data.bot_name);
    if (safeBotName) {
      suffix = `-${safeBotName}`;
    }
  } else if (platformType === 'weixin_oc' || platformType === 'dingtalk') {
    suffix = buildRandomPlatformIdSuffix();
  }

  if (!suffix) {
    return;
  }

  if (
    (platformType === 'weixin_oc' || platformType === 'dingtalk') &&
    /_[a-z]{4}$/.test(currentId)
  ) {
    return;
  }

  state.selectedPlatformConfig.id = currentId.endsWith(suffix)
    ? currentId
    : `${currentId}${suffix}`;
}

async function getPlatformConfigs(platformId: string) {
  state.platformRoutesLoaded = false;
  if (!platformId) {
    state.platformRoutes = [];
    return;
  }

  try {
    const routesRes = await configRouteApi.list();
    const routingTable = normalizeRoutingTable(routesRes.data.data.routing);
    const routes: PlatformRoute[] = [];

    for (const [umop, configId] of Object.entries(routingTable)) {
      const parsedUmop = parseUmop(umop);
      if (isParsedUmopMatchPlatform(parsedUmop, platformId)) {
        routes.push({
          umop,
          originalUmop: umop,
          sourceMode: 'manual',
          sourceUmo: parsedUmop?.sessionId === '*' ? '' : umop,
          messageType: parsedUmop?.messageType || '*',
          sessionId: parsedUmop?.sessionId || '*',
          configId,
        });
      }
    }

    state.platformRoutes = routes;
    if (state.platformRoutes.length === 0) {
      state.platformRoutes.push({
        umop: null,
        originalUmop: null,
        sourceMode: 'manual',
        sourceUmo: '',
        messageType: '*',
        sessionId: '*',
        configId: 'default',
      });
    }
    state.platformRoutesLoaded = true;
  } catch (error) {
    console.error('获取平台路由配置失败:', error);
    state.platformRoutes = [];
    state.platformRoutesLoaded = false;
  }
}

async function loadKnownRouteUmos() {
  if (state.loadingKnownRouteUmos) {
    return;
  }

  state.loadingKnownRouteUmos = true;
  try {
    const res = await sessionApi.activeUmos();
    if (res.data.status === 'ok') {
      const umos = normalizeStringArray(res.data.data?.umos);
      state.knownRouteUmos = Array.from(
        new Set([...state.knownRouteUmos, ...umos]),
      );
      mergeKnownRouteUmoInfos(
        normalizeKnownRouteUmoInfos(res.data.data?.umo_infos),
      );
    }
  } catch (error) {
    console.error('获取已有消息来源失败:', error);
  } finally {
    state.loadingKnownRouteUmos = false;
  }
}

function mergeKnownRouteUmoInfos(infos: KnownRouteUmoInfo[]) {
  const next = { ...state.knownRouteUmoInfoMap };
  for (const info of infos) {
    next[info.umo] = { ...(next[info.umo] || {}), ...info };
  }
  state.knownRouteUmoInfoMap = next;
}

function toggleRouteSourceMode(route: PlatformRoute) {
  const nextMode: PlatformRoute['sourceMode'] =
    getRouteSourceMode(route) === 'known' ? 'manual' : 'known';
  route.sourceMode = nextMode;
  if (nextMode === 'known') {
    void loadKnownRouteUmos();
  }
}

function applyKnownRouteSource(route: PlatformRoute, umo: string | null) {
  if (!umo) {
    route.sourceUmo = '';
    return;
  }

  const parsed = parseUmop(umo);
  if (!parsed) {
    return;
  }
  route.sourceUmo = umo;
  route.messageType = parsed.messageType || '*';
  route.sessionId = parsed.sessionId || '*';
}

function addNewRoute() {
  state.platformRoutes.push({
    umop: null,
    originalUmop: null,
    sourceMode: 'manual',
    sourceUmo: '',
    messageType: '*',
    sessionId: '*',
    configId: 'default',
  });
}

function deleteRoute(index: number) {
  state.platformRoutes.splice(index, 1);
}

function moveRouteUp(index: number) {
  if (index > 0) {
    const current = state.platformRoutes[index];
    state.platformRoutes[index] = state.platformRoutes[index - 1];
    state.platformRoutes[index - 1] = current;
    state.platformRoutes = [...state.platformRoutes];
  }
}

function moveRouteDown(index: number) {
  if (index < state.platformRoutes.length - 1) {
    const current = state.platformRoutes[index];
    state.platformRoutes[index] = state.platformRoutes[index + 1];
    state.platformRoutes[index + 1] = current;
    state.platformRoutes = [...state.platformRoutes];
  }
}

async function saveRoutesInternal() {
  if (!state.platformRoutesLoaded) {
    throw new Error(tm('messages.routingLoadRequired'));
  }

  const originalPlatformId =
    state.originalUpdatingPlatformId ??
    getString(updatingPlatformConfig.value.id);
  const newPlatformId =
    getString(updatingPlatformConfig.value.id) ?? originalPlatformId;

  if (!originalPlatformId && !newPlatformId) {
    throw new Error(tm('messages.platformIdMissing'));
  }

  try {
    const routesRes = await configRouteApi.list();
    const fullRoutingTable = normalizeRoutingTable(routesRes.data.data.routing);

    for (const umop of Object.keys(fullRoutingTable)) {
      if (
        (originalPlatformId && isUmopMatchPlatform(umop, originalPlatformId)) ||
        (newPlatformId && isUmopMatchPlatform(umop, newPlatformId))
      ) {
        delete fullRoutingTable[umop];
      }
    }

    const platformIdForRoute = newPlatformId || originalPlatformId;
    for (const route of state.platformRoutes) {
      if (!route.configId || !platformIdForRoute) {
        continue;
      }
      const messageType = route.messageType === '*' ? '*' : route.messageType;
      const sessionId = route.sessionId === '*' ? '*' : route.sessionId;
      fullRoutingTable[`${platformIdForRoute}:${messageType}:${sessionId}`] =
        route.configId;
    }

    await configRouteApi.replace({
      routing: fullRoutingTable,
    });
  } catch (error) {
    console.error('保存路由表失败:', error);
    throw new Error(
      tm('messages.routingSaveFailed', {
        message: resolveErrorMessage(
          error,
          tm('messages.platformUpdateFailed'),
        ),
      }),
    );
  }
}

function toggleEditMode() {
  state.isEditingRoutes = !state.isEditingRoutes;
}

function toggleConfigSection() {
  state.showConfigSection = !state.showConfigSection;
}

function prepareData() {
  void getConfigInfoList();
  const platformId = getString(updatingPlatformConfig.value.id);
  if (updatingMode.value && platformId) {
    void getPlatformConfigs(platformId);
  }
}

function scrollDialogToBottom() {
  const container = dialogScrollContainer.value;
  const element =
    container && '$el' in container ? (container.$el ?? null) : container;
  if (!(element instanceof HTMLElement)) {
    return;
  }

  const scrollOptions = {
    top: element.scrollHeight,
    behavior: 'smooth' as const,
  };
  if (typeof element.scrollTo === 'function') {
    element.scrollTo(scrollOptions);
  } else {
    element.scrollTop = element.scrollHeight;
  }
}
</script>

<style scoped>
.platform-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.platform-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: var(--astrbot-space-4);
}

.platform-dialog__actions {
  flex-shrink: 0;
}

.platform-config-select {
  min-width: 200px;
  max-width: 30%;
}

@media (max-width: 600px) {
  .platform-dialog__card {
    max-height: calc(100dvh - 24px);
  }

  .platform-dialog__content {
    padding-right: 16px;
  }
}
</style>

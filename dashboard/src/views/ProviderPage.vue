<template>
  <div class="provider-page">
    <v-container fluid class="pa-0">
      <div class="provider-tabs-scroll">
        <div
          class="provider-tabs"
          role="tablist"
          :aria-label="tm('providerTypes.title')"
        >
          <button
            v-for="type in providerTypes"
            :key="type.value"
            type="button"
            class="provider-tab"
            :class="{
              'provider-tab--active': selectedProviderType === type.value,
            }"
            role="tab"
            :aria-selected="selectedProviderType === type.value"
            @click="selectedProviderType = type.value"
          >
            <v-icon :icon="type.icon" size="16" />
            <span>{{ type.label }}</span>
          </button>
          <ConfigDocsLink docs="providers/start.html" />
        </div>
      </div>

      <div class="provider-content">
        <div class="provider-workbench">
          <div class="provider-workbench__sidebar">
            <ProviderSourcesPanel
              :displayed-provider-sources="
                selectedProviderType === 'chat_completion'
                  ? displayedProviderSources
                  : displayedLegacyProviders
              "
              :selected-provider-source="
                (selectedProviderType === 'chat_completion'
                  ? selectedProviderSource
                  : selectedLegacyProvider) ?? undefined
              "
              :available-source-types="availableSourceTypes"
              :title="
                selectedProviderType === 'chat_completion'
                  ? ''
                  : tm('providers.title')
              "
              :empty-text="
                selectedProviderType === 'chat_completion' ? '' : getEmptyText()
              "
              :select-hint="
                selectedProviderType === 'chat_completion'
                  ? ''
                  : tm('providers.selectHint')
              "
              :delete-label="
                selectedProviderType === 'chat_completion'
                  ? ''
                  : tm('providers.deleteProvider')
              "
              :loading="loadingSources"
              :tm="providerTm"
              :resolve-source-icon="resolveSourceIcon"
              :is-monochrome-source-icon="isMonochromeSourceIcon"
              :get-source-display-name="getSourceDisplayName"
              @add-provider-source="
                selectedProviderType === 'chat_completion'
                  ? addProviderSource($event)
                  : addLegacyProvider($event)
              "
              @select-provider-source="
                selectedProviderType === 'chat_completion'
                  ? selectProviderSource($event)
                  : selectLegacyProvider($event)
              "
              @delete-provider-source="
                selectedProviderType === 'chat_completion'
                  ? deleteProviderSource($event)
                  : deleteLegacyProvider($event)
              "
            />
          </div>

          <div class="provider-workbench__divider"></div>

          <div class="provider-workbench__main">
            <template v-if="selectedProviderType === 'chat_completion'">
              <ProviderChatCompletionBody
                v-model:model-search="modelSearch"
                :selected-provider-source="selectedProviderSource"
                :title="selectedProviderSource?.id || ''"
                :subtitle="selectedProviderSource?.api_base || ''"
                :basic-source-config="basicSourceConfig"
                :advanced-source-config="advancedSourceConfig"
                :provider-source-schema="providerSourceSchema"
                :entries="filteredMergedModelEntries"
                :available-count="availableModels.length"
                :loading-models="loadingModels"
                :saving-source="savingSource"
                :is-source-modified="isSourceModified"
                :supports-image-input="supportsImageInput"
                :supports-audio-input="supportsAudioInput"
                :supports-tool-call="supportsToolCall"
                :supports-reasoning="supportsReasoning"
                :format-context-limit="formatContextLimit"
                :testing-providers="testingProviders"
                :tm="tm"
                @save="saveProviderSource"
                @fetch-models="fetchAvailableModels"
                @open-manual-model="openManualModelDialog"
                @open-provider-edit="openProviderEdit"
                @toggle-provider-enable="toggleProviderEnable"
                @test-provider="testProvider"
                @delete-provider="deleteProvider"
                @add-model-provider="openModelAddDialog"
              />
            </template>

            <template v-else>
              <div v-if="selectedLegacyProvider" class="provider-config-shell">
                <div class="provider-config-header">
                  <div class="provider-config-headline">
                    <div class="provider-config-title">
                      {{
                        newSelectedProviderConfig.id ||
                        selectedLegacyProvider.id
                      }}
                    </div>
                    <div class="provider-config-subtitle">
                      {{
                        newSelectedProviderConfig.api_base ||
                        newSelectedProviderConfig.embedding_api_base ||
                        newSelectedProviderConfig.rerank_api_base ||
                        newSelectedProviderConfig.type ||
                        'N/A'
                      }}
                    </div>
                  </div>

                  <div class="provider-config-actions d-flex align-center ga-2">
                    <v-btn
                      v-if="updatingMode"
                      color="primary"
                      prepend-icon="mdi-connection"
                      :loading="
                        isProviderTesting(selectedLegacyProvider.id ?? '')
                      "
                      :disabled="selectedLegacyProvider.enable === false"
                      variant="text"
                      rounded="md"
                      @click="testSingleProvider(selectedLegacyProvider)"
                    >
                      {{ tm('availability.test') }}
                    </v-btn>
                    <v-btn
                      color="primary"
                      prepend-icon="mdi-content-save-outline"
                      :loading="loading"
                      :disabled="!isLegacyProviderModified"
                      variant="tonal"
                      rounded="md"
                      @click="saveLegacyProvider"
                    >
                      {{ tm('dialogs.config.save') }}
                    </v-btn>
                  </div>
                </div>

                <v-divider></v-divider>

                <div class="provider-config-body">
                  <section class="provider-section config-form">
                    <div class="provider-section-head">
                      <div class="provider-section-title">
                        {{ tm('providers.settings') }}
                      </div>
                    </div>
                    <AstrBotConfig
                      :iterable="newSelectedProviderConfig"
                      :metadata="configSchema"
                      metadata-key="provider"
                      :is-editing="updatingMode"
                    />
                  </section>
                </div>
              </div>

              <div v-else class="provider-empty-state">
                <v-icon size="48" color="on-surface-variant"
                  >mdi-cursor-default-click</v-icon
                >
                <p class="mt-2">{{ tm('providers.selectHint') }}</p>
              </div>
            </template>
          </div>
        </div>
      </div>
    </v-container>

    <ProviderManualModelDialog
      v-model="showManualModelDialog"
      v-model:manual-model-id="manualModelId"
      :manual-provider-id="manualProviderId"
      :tm="tm"
      @confirm="confirmManualModel"
    />

    <ProviderEditDialog
      v-model="showProviderEditDialog"
      :provider-edit-data="providerEditData"
      :provider-model-config-schema="providerModelConfigSchema"
      :saving-providers="savingProviders"
      :title="providerEditDialogTitle"
      :tm="tm"
      @save="saveEditedProvider"
    />

    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />

    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="3000"
      location="top"
    >
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, unref, watch } from 'vue';
import { providerApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import ConfigDocsLink from '@/components/shared/ConfigDocsLink.vue';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import ProviderChatCompletionBody from '@/components/provider/ProviderChatCompletionBody.vue';
import ProviderEditDialog from '@/components/provider/ProviderEditDialog.vue';
import ProviderManualModelDialog from '@/components/provider/ProviderManualModelDialog.vue';
import ProviderSourcesPanel from '@/components/provider/ProviderSourcesPanel.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useProviderModelConfigDialog } from '@/composables/useProviderModelConfigDialog';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useManualModelDialog } from '@/composables/useManualModelDialog';
import { useProviderSources } from '@/composables/useProviderSources';
import { runProviderMutationWithStepUp } from '@/utils/stepUp';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { validateJevClassifierConfig } from '@/utils/jevClassifierConfig';

const props = defineProps({
  defaultTab: {
    type: String,
    default: 'chat_completion',
  },
});

type ConfigRecord = Record<string, unknown>;

interface LegacyProvider {
  id?: string;
  type?: string;
  provider_type?: string;
  enable?: boolean;
  [key: string]: unknown;
  [key: symbol]: unknown;
}

interface LegacyProviderConfig {
  id?: string;
  api_base?: string;
  embedding_api_base?: string;
  rerank_api_base?: string;
  type?: string;
  [key: string]: unknown;
}

type ProviderDialogOptions = Parameters<typeof useProviderModelConfigDialog>[0];

const { tm } = useModuleI18n('features/provider');
const providerTm = tm as (
  key: string,
  params?: Record<string, unknown>,
) => string;
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const snackbar = ref({
  show: false,
  message: '',
  color: 'success',
});

function showMessage(message: string, color = 'success') {
  snackbar.value = { show: true, message, color };
}

const {
  providers,
  selectedProviderType,
  selectedProviderSource,
  availableModels,
  loadingSources,
  loadingModels,
  savingSource,
  testingProviders,
  isSourceModified,
  configSchema,
  providerSourceSchema,
  manualModelId,
  modelSearch,
  providerTypes,
  availableSourceTypes,
  displayedProviderSources,
  filteredMergedModelEntries,
  filteredProviders,
  basicSourceConfig,
  advancedSourceConfig,
  manualProviderId,
  resolveSourceIcon,
  isMonochromeSourceIcon,
  getSourceDisplayName,
  supportsImageInput,
  supportsAudioInput,
  supportsToolCall,
  supportsReasoning,
  formatContextLimit,
  updateDefaultTab,
  selectProviderSource,
  addProviderSource,
  deleteProviderSource,
  saveProviderSource,
  fetchAvailableModels,
  buildModelProviderConfig,
  deleteProvider,
  modelAlreadyConfigured,
  testProvider,
  toggleProviderEnable,
  loadConfig,
} = useProviderSources({
  defaultTab: props.defaultTab,
  tm: providerTm,
  showMessage,
  requestStepUp,
});

const unsavedLegacyProviderMarker = Symbol('unsavedLegacyProvider');
const legacyProviderDrafts = ref<LegacyProvider[]>([]);
const selectedLegacyProvider = ref<LegacyProvider | null>(null);
const newSelectedProviderConfig = ref<LegacyProviderConfig>({});
const newProviderOriginalId = ref('');
const updatingMode = ref(false);
const loading = ref(false);
const isLegacyProviderModified = ref(false);
let suppressLegacyProviderWatch = false;

const displayedLegacyProviders = computed(() => [
  ...unref(filteredProviders),
  ...legacyProviderDrafts.value.filter(
    (provider) => provider.provider_type === selectedProviderType.value,
  ),
]);

const {
  showProviderEditDialog,
  providerEditData,
  savingProviders,
  providerModelConfigSchema,
  providerEditDialogTitle,
  openProviderEdit,
  openModelAddDialog,
  saveEditedProvider,
} = useProviderModelConfigDialog({
  selectedProviderSource,
  configSchema: configSchema as ProviderDialogOptions['configSchema'],
  buildModelProviderConfig,
  modelAlreadyConfigured,
  loadConfig,
  tm,
  showMessage,
  requestStepUp,
});

const { showManualModelDialog, openManualModelDialog, confirmManualModel } =
  useManualModelDialog({
    selectedProviderSource,
    manualModelId,
    modelAlreadyConfigured,
    openModelAddDialog,
    tm,
    showMessage,
  });

watch(
  () => props.defaultTab,
  (val) => {
    updateDefaultTab(val);
  },
);

watch(selectedProviderType, () => {
  selectedLegacyProvider.value = null;
  newProviderOriginalId.value = '';
  updatingMode.value = false;
  isLegacyProviderModified.value = false;
  suppressLegacyProviderWatch = true;
  newSelectedProviderConfig.value = {};
  void nextTick(() => {
    suppressLegacyProviderWatch = false;
  });
});

watch(
  newSelectedProviderConfig,
  (config) => {
    if (suppressLegacyProviderWatch || !selectedLegacyProvider.value) return;

    isLegacyProviderModified.value = true;
    if (selectedLegacyProvider.value[unsavedLegacyProviderMarker]) {
      Object.assign(
        selectedLegacyProvider.value,
        JSON.parse(JSON.stringify(config)),
      );
    }
  },
  { deep: true },
);

function getEmptyText() {
  const selectedType = unref(providerTypes).find(
    (type) => type.value === selectedProviderType.value,
  );
  return tm('providers.empty.typed', {
    type: selectedType?.label || selectedProviderType.value,
  });
}

function addLegacyProvider(name: string) {
  const template = configSchema.value.provider?.config_template?.[name];
  if (!template) {
    showMessage(tm('dialogs.addProvider.noTemplates'), 'error');
    return;
  }

  const draft = JSON.parse(JSON.stringify(template)) as LegacyProvider;
  const existingIds = new Set([
    ...providers.value.map((provider) => provider.id),
    ...legacyProviderDrafts.value.map((provider) => provider.id),
  ]);
  const baseId = String(draft.id || name);
  let nextId = baseId;
  let counter = 1;
  while (existingIds.has(nextId)) {
    nextId = `${baseId}_${counter}`;
    counter += 1;
  }
  draft.id = nextId;
  draft[unsavedLegacyProviderMarker] = true;
  legacyProviderDrafts.value.push(draft);
  selectLegacyProvider(draft);
}

function cloneConfigValue(value: unknown) {
  if (typeof value !== 'object' || value === null) {
    return value;
  }
  return Array.isArray(value) ? [...value] : { ...(value as ConfigRecord) };
}

function mergeReferenceValue(
  target: ConfigRecord,
  source: ConfigRecord | null | undefined,
  key: string,
  referenceValue: unknown,
) {
  if (typeof referenceValue === 'object' && referenceValue !== null) {
    if (!(key in target)) {
      target[key] = Array.isArray(referenceValue) ? [...referenceValue] : {};
    }
    if (!Array.isArray(referenceValue)) {
      const sourceValue = source?.[key];
      mergeConfigWithOrder(
        target[key] as ConfigRecord,
        sourceValue ? (sourceValue as ConfigRecord) : {},
        referenceValue as ConfigRecord,
      );
    }
    return;
  }
  if (!(key in target)) {
    target[key] = referenceValue;
  }
}

function mergeConfigWithOrder(
  target: ConfigRecord,
  source: ConfigRecord | null | undefined,
  reference: ConfigRecord,
) {
  if (source && typeof source === 'object' && !Array.isArray(source)) {
    for (const key in source) {
      if (Object.hasOwn(source, key)) {
        target[key] = cloneConfigValue(source[key]);
      }
    }
  }

  for (const key in reference) {
    mergeReferenceValue(target, source, key, reference[key]);
  }
}

function selectLegacyProvider(provider: LegacyProvider) {
  selectedLegacyProvider.value = provider;
  newProviderOriginalId.value = provider[unsavedLegacyProviderMarker]
    ? ''
    : (provider.id ?? '');
  suppressLegacyProviderWatch = true;
  newSelectedProviderConfig.value = {};

  const templates = configSchema.value.provider?.config_template || {};
  let defaultConfig: ConfigRecord = {};
  for (const key in templates) {
    if (templates[key]?.type === provider.type) {
      defaultConfig = templates[key];
      break;
    }
  }

  if (defaultConfig) {
    mergeConfigWithOrder(
      newSelectedProviderConfig.value,
      provider,
      defaultConfig,
    );
  }

  updatingMode.value = !provider[unsavedLegacyProviderMarker];
  isLegacyProviderModified.value = Boolean(
    provider[unsavedLegacyProviderMarker],
  );
  void nextTick(() => {
    suppressLegacyProviderWatch = false;
  });
}

async function saveLegacyProvider() {
  if (!selectedLegacyProvider.value) return;

  const validationKey = validateJevClassifierConfig(
    newSelectedProviderConfig.value,
  );
  if (validationKey) {
    showMessage(tm(`jevClassifier.validation.${validationKey}`), 'error');
    return;
  }

  loading.value = true;
  const wasUpdating = updatingMode.value;
  const selectedDraft = selectedLegacyProvider.value;
  const savedId = newSelectedProviderConfig.value.id;
  const providerId = (
    wasUpdating
      ? newProviderOriginalId.value || savedId
      : String(savedId || 'new')
  ) as string;
  try {
    if (wasUpdating) {
      const res = await runProviderMutationWithStepUp(
        (stepUp) =>
          providerApi.update(
            providerId,
            newSelectedProviderConfig.value,
            stepUp,
          ),
        providerId,
        requestStepUp,
      );
      if (!res) return;
      if (res.data.status === 'error') {
        throw new Error(res.data.message || tm('providerSources.saveError'));
      }
      showMessage(res.data.message || tm('messages.success.update'));
    } else {
      const res = await runProviderMutationWithStepUp(
        (stepUp) => providerApi.create(newSelectedProviderConfig.value, stepUp),
        providerId,
        requestStepUp,
      );
      if (!res) return;
      if (res.data.status === 'error') {
        throw new Error(res.data.message || tm('providerSources.saveError'));
      }
      showMessage(res.data.message || tm('messages.success.add'));
      legacyProviderDrafts.value = legacyProviderDrafts.value.filter(
        (provider) => provider !== selectedDraft,
      );
    }

    await loadConfig();
    const savedProvider = providers.value.find(
      (provider) => provider.id === savedId,
    );
    if (savedProvider) {
      selectLegacyProvider(savedProvider);
      isLegacyProviderModified.value = false;
    }
  } catch (err) {
    showMessage(
      resolveErrorMessage(err, tm('providerSources.saveError')),
      'error',
    );
  } finally {
    loading.value = false;
  }
}

async function deleteLegacyProvider(provider: LegacyProvider) {
  if (provider[unsavedLegacyProviderMarker]) {
    legacyProviderDrafts.value = legacyProviderDrafts.value.filter(
      (draft) => draft !== provider,
    );
    if (selectedLegacyProvider.value === provider) {
      selectedLegacyProvider.value = null;
      newSelectedProviderConfig.value = {};
      newProviderOriginalId.value = '';
      updatingMode.value = false;
      isLegacyProviderModified.value = false;
    }
    return;
  }

  const deleted = await deleteProvider(provider);
  if (deleted && selectedLegacyProvider.value?.id === provider.id) {
    selectedLegacyProvider.value = null;
    newSelectedProviderConfig.value = {};
    newProviderOriginalId.value = '';
    updatingMode.value = false;
    isLegacyProviderModified.value = false;
  }
}

function isProviderTesting(providerId: string) {
  return testingProviders.value.includes(providerId);
}

async function testSingleProvider(provider: LegacyProvider) {
  if (isProviderTesting(provider.id ?? '')) return;
  if (provider.enable === false) {
    showMessage(tm('providerSources.disabled'), 'error');
    return;
  }

  await testProvider(provider);
}
</script>

<style scoped>
.provider-page {
  --provider-surface: rgb(var(--v-theme-surface));
  --provider-border: rgb(var(--v-theme-outline-variant));
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  width: 100%;
}

.provider-page > .v-container {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.provider-tabs-scroll {
  flex: 0 0 auto;
  overflow-x: auto;
  padding: 4px 12px 8px;
  scrollbar-width: none;
}

.provider-tabs-scroll::-webkit-scrollbar {
  display: none;
}

.provider-tabs {
  align-items: center;
  display: inline-flex;
  gap: 2px;
  min-width: max-content;
}

.provider-tab {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  white-space: nowrap;
}

.provider-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.provider-tab--active {
  background: rgba(var(--v-theme-on-surface), 0.065);
  color: rgba(var(--v-theme-on-surface), 0.86);
}

.provider-tab--active:hover {
  background: rgba(var(--v-theme-on-surface), 0.09);
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.provider-content {
  display: flex;
  flex: 1;
  margin: 0 auto;
  max-width: 1200px;
  min-height: 0;
  padding: 16px 12px 12px;
  width: 100%;
}

.provider-workbench {
  border: 1px solid var(--provider-border);
  border-radius: 8px;
  background: var(--provider-surface);
  display: grid;
  flex: 1;
  grid-template-columns: minmax(280px, 320px) 1px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  width: 100%;
}

.provider-workbench__sidebar,
.provider-workbench__main {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.provider-workbench__divider {
  background: var(--provider-border);
}

.provider-workbench__main {
  display: flex;
  flex-direction: column;
  height: 100%;
}

@media (max-width: 960px) {
  .provider-workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1px minmax(0, 1fr);
  }

  .provider-workbench__divider {
    height: 1px;
  }
}

@media (max-width: 600px) {
  .provider-tabs-scroll {
    padding-inline: 4px;
  }

  .provider-workbench {
    border-radius: 8px;
  }

  .provider-tab {
    padding-inline: 11px;
  }
}
</style>

<style scoped src="@/styles/config-form.css"></style>

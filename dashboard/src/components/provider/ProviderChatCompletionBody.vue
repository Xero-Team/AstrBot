<template>
  <div v-if="selectedProviderSource" class="provider-config-shell">
    <div class="provider-config-header">
      <div class="provider-config-headline">
        <div class="provider-config-title">{{ title }}</div>
        <div class="provider-config-subtitle">{{ subtitle || 'N/A' }}</div>
      </div>

      <div class="provider-config-actions">
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :loading="savingSource"
          :disabled="!isSourceModified"
          variant="tonal"
          rounded="md"
          @click="emit('save')"
        >
          {{ tm('providerSources.save') }}
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
          v-if="basicSourceConfig"
          :iterable="basicSourceConfig"
          :metadata="providerSourceSchema"
          :field-links="providerSourceFieldLinks"
          metadata-key="provider"
          :is-editing="true"
        />
      </section>

      <v-divider v-if="advancedSourceConfig"></v-divider>

      <section v-if="advancedSourceConfig" class="provider-section config-form">
        <div class="provider-section-head">
          <div class="provider-section-title">
            {{ tm('providerSources.advancedConfig') }}
          </div>
        </div>
        <AstrBotConfig
          :iterable="advancedSourceConfig"
          :metadata="providerSourceSchema"
          metadata-key="provider"
          :is-editing="true"
        />
      </section>

      <v-divider></v-divider>

      <section class="provider-section provider-section--models">
        <ProviderModelsPanel
          v-model:model-search="modelSearchProxy"
          :entries="entries"
          :available-count="availableCount"
          :loading-models="loadingModels"
          :is-source-modified="isSourceModified"
          :supports-image-input="supportsImageInput"
          :supports-audio-input="supportsAudioInput"
          :supports-tool-call="supportsToolCall"
          :supports-reasoning="supportsReasoning"
          :format-context-limit="formatContextLimit"
          :saving-providers="savingProviders"
          :testing-providers="testingProviders"
          :tm="tm"
          @fetch-models="emit('fetch-models')"
          @open-manual-model="emit('open-manual-model')"
          @open-provider-edit="emit('open-provider-edit', $event)"
          @toggle-provider-enable="emit('toggle-provider-enable', $event)"
          @test-provider="emit('test-provider', $event)"
          @delete-provider="emit('delete-provider', $event)"
          @add-model-provider="emit('add-model-provider', $event)"
        />
      </section>
    </div>
  </div>

  <div v-else class="provider-empty-state">
    <v-icon size="48" color="on-surface-variant"
      >mdi-cursor-default-click</v-icon
    >
    <p class="mt-2">{{ tm('providerSources.selectHint') }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, type PropType } from 'vue';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import ProviderModelsPanel from '@/components/provider/ProviderModelsPanel.vue';
import { normalizeTextInput } from '@/utils/inputValue';
import type { ProviderModelMetadata } from '@/utils/providerMetadata';

interface ProviderSourceItem {
  id?: string;
  api_base?: string;
  provider?: string;
  [key: string]: unknown;
}

interface ProviderItem {
  id?: string;
  model?: string;
  enable?: boolean;
  modalities?: string[];
  [key: string]: unknown;
}

interface ConfiguredModelEntry {
  type: 'configured';
  provider: ProviderItem;
  metadata: ProviderModelMetadata | null;
  hasModelMetadata?: boolean;
}

interface AvailableModelEntry {
  type: 'available';
  model: string;
  metadata: ProviderModelMetadata | null;
  hasModelMetadata?: boolean;
}

type MergedModelEntry = ConfiguredModelEntry | AvailableModelEntry;

interface FieldLink {
  label: string;
  href: string;
}

type SupportsCapability = (
  meta: ProviderModelMetadata | null | undefined,
) => boolean;

const props = defineProps({
  selectedProviderSource: {
    type: Object as PropType<ProviderSourceItem | null>,
    default: null,
  },
  title: {
    type: String,
    default: '',
  },
  subtitle: {
    type: String,
    default: '',
  },
  basicSourceConfig: {
    type: Object as PropType<Record<string, unknown> | null>,
    default: null,
  },
  advancedSourceConfig: {
    type: Object as PropType<Record<string, unknown> | null>,
    default: null,
  },
  providerSourceSchema: {
    type: Object as PropType<Record<string, unknown>>,
    default: () => ({}),
  },
  providerSourceFieldLinks: {
    type: Object as PropType<Record<string, FieldLink | undefined>>,
    default: () => ({}),
  },
  modelSearch: {
    type: String,
    default: '',
  },
  entries: {
    type: Array as PropType<MergedModelEntry[]>,
    default: () => [],
  },
  availableCount: {
    type: Number,
    default: 0,
  },
  loadingModels: {
    type: Boolean,
    default: false,
  },
  savingSource: {
    type: Boolean,
    default: false,
  },
  isSourceModified: {
    type: Boolean,
    default: false,
  },
  supportsImageInput: {
    type: Function as PropType<SupportsCapability>,
    required: true,
  },
  supportsAudioInput: {
    type: Function as PropType<SupportsCapability>,
    required: true,
  },
  supportsToolCall: {
    type: Function as PropType<SupportsCapability>,
    required: true,
  },
  supportsReasoning: {
    type: Function as PropType<SupportsCapability>,
    required: true,
  },
  formatContextLimit: {
    type: Function as PropType<
      (meta: ProviderModelMetadata | null | undefined) => string
    >,
    required: true,
  },
  savingProviders: {
    type: Array as PropType<string[]>,
    default: () => [],
  },
  testingProviders: {
    type: Array as PropType<string[]>,
    default: () => [],
  },
  tm: {
    type: Function as PropType<
      (key: string, params?: Record<string, string | number>) => string
    >,
    required: true,
  },
});

const emit = defineEmits([
  'update:modelSearch',
  'save',
  'fetch-models',
  'open-manual-model',
  'open-provider-edit',
  'toggle-provider-enable',
  'test-provider',
  'delete-provider',
  'add-model-provider',
]);

const modelSearchProxy = computed({
  get: () => props.modelSearch,
  set: (val) => void emit('update:modelSearch', normalizeTextInput(val)),
});
</script>

<style scoped>
.provider-config-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.provider-config-header {
  background: rgb(var(--v-theme-surface));
  display: flex;
  flex: 0 0 auto;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--astrbot-space-4);
  padding: var(--astrbot-space-4) var(--astrbot-space-6);
  position: relative;
  z-index: 1;
}

.provider-config-shell > :deep(.v-divider) {
  flex: 0 0 auto;
}

.provider-config-headline {
  min-width: 0;
}

.provider-config-title {
  font-size: 24px;
  line-height: 32px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.provider-config-subtitle {
  margin-top: var(--astrbot-space-2);
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 13px;
  line-height: 18px;
  overflow-wrap: anywhere;
}

.provider-config-actions {
  flex-shrink: 0;
}

.provider-config-body {
  flex: 1;
  min-height: 0;
  overscroll-behavior: contain;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.provider-section {
  padding: var(--astrbot-space-4) var(--astrbot-space-6);
}

.provider-section--models {
  padding-top: var(--astrbot-space-4);
}

.provider-section-head {
  margin-bottom: var(--astrbot-space-2);
}

.provider-section-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.provider-empty-state {
  flex: 1;
  min-height: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: rgb(var(--v-theme-on-surface-variant));
}

@media (max-width: 960px) {
  .provider-config-header {
    flex-direction: column;
    align-items: stretch;
    padding: var(--astrbot-space-4);
  }

  .provider-config-actions :deep(.v-btn) {
    width: 100%;
  }

  .provider-config-actions {
    align-items: stretch !important;
    flex-direction: column;
    width: 100%;
  }

  .provider-section {
    padding: var(--astrbot-space-4);
  }
}

@media (max-width: 600px) {
  .provider-config-title {
    font-size: 18px;
  }

  .provider-empty-state {
    min-height: 260px;
    padding: var(--astrbot-space-6);
  }
}
</style>

<style scoped src="@/styles/config-form.css"></style>

<template>
  <div class="w-100">
    <!-- Special handling for specific metadata types -->
    <template v-if="itemMeta?._special === 'umo'">
      <UmoSelector
        :model-value="modelValue"
        :multiple="itemMeta?.type === 'list'"
        :readonly="Boolean(itemMeta?.readonly)"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'sender_id'">
      <SenderSelector
        :model-value="modelValue"
        :readonly="Boolean(itemMeta?.readonly)"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider'">
      <ProviderSelector
        :model-value="modelValue as ProviderSelectorValue"
        @update:model-value="emitUpdate"
        :provider-type="'chat_completion'"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_classifier'">
      <ProviderSelector
        :model-value="modelValue as ProviderSelectorValue"
        @update:model-value="emitUpdate"
        :provider-type="'classifier'"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_stt'">
      <ProviderSelector
        :model-value="modelValue as ProviderSelectorValue"
        @update:model-value="emitUpdate"
        :provider-type="'speech_to_text'"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_tts'">
      <ProviderSelector
        :model-value="modelValue as ProviderSelectorValue"
        @update:model-value="emitUpdate"
        :provider-type="'text_to_speech'"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_providers'">
      <ProviderSelector
        :model-value="modelValue as ProviderSelectorValue"
        @update:model-value="emitUpdate"
        :provider-type="'chat_completion'"
        :multiple="true"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'provider_pool'">
      <ProviderSelector
        :model-value="modelValue as ProviderSelectorValue"
        @update:model-value="emitUpdate"
        :provider-type="'chat_completion'"
        :button-text="t('core.shared.providerSelector.selectProviderPool')"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_prompt'">
      <PromptSelector
        :model-value="modelValue as OptionalString"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'prompt_pool'">
      <PromptSelector
        :model-value="modelValue as OptionalString"
        @update:model-value="emitUpdate"
        :button-text="t('core.shared.promptSelector.selectPromptPool')"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_knowledgebase'">
      <KnowledgeBaseSelector
        :model-value="modelValue as OptionalStringArray"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_plugin_set'">
      <PluginSetSelector
        :model-value="modelValue as OptionalStringArray"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_plugin_loop_routes'">
      <PluginLoopSelector
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_mcp_loop_routes'">
      <CapabilityLoopSelector
        kind="mcp"
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_skill_loop_routes'">
      <CapabilityLoopSelector
        kind="skill"
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_coding_agents'">
      <CodingAgentsEditor
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 't2i_template'">
      <T2ITemplateEditor />
    </template>
    <template v-else-if="itemMeta?._special === 'dashboard_totp_manager'">
      <DashboardTotpManager
        :model-value="Boolean(modelValue)"
        :config-root="configRoot as OptionalRecord"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'local_permission_matrix'">
      <LocalPermissionMatrix
        :model-value="modelValue as OptionalRecord"
        @update:model-value="emitUpdate"
        class="config-field config-field--full-width"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'get_embedding_dim'">
      <div class="d-flex align-center gap-2">
        <v-text-field
          :model-value="modelValue"
          @update:model-value="emitUpdate"
          density="compact"
          variant="outlined"
          class="config-field"
          type="number"
          hide-details
          :aria-label="fieldAriaLabel"
        ></v-text-field>
        <v-btn
          color="primary"
          variant="tonal"
          size="small"
          @click="$emit('get-embedding-dim')"
          :loading="loading"
          class="ml-2"
        >
          {{ t('core.common.autoDetect') }}
        </v-btn>
      </div>
    </template>

    <div
      v-else-if="
        itemMeta?.type === 'list' &&
        itemMeta?.options &&
        itemMeta?.render_type === 'checkbox'
      "
      class="checkbox-group d-flex flex-wrap"
    >
      <v-checkbox
        v-for="(option, optionIndex) in itemMeta.options"
        :key="optionIndex"
        :model-value="modelValue"
        @update:model-value="emitUpdate"
        :label="getLabel(itemMeta, optionIndex, option)"
        :value="option"
        class="config-checkbox"
        color="primary"
        density="compact"
        hide-details
      ></v-checkbox>
    </div>

    <v-autocomplete
      v-else-if="itemMeta?.type === 'list' && itemMeta?.options"
      :model-value="modelValue as OptionalUnknownArray"
      @update:model-value="
        (val) => {
          emitUpdate(val);
          listSearchText = '';
        }
      "
      v-model:search="listSearchText"
      :items="listSelectItems"
      item-title="title"
      item-value="value"
      :disabled="itemMeta?.readonly"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      chips
      multiple
      :aria-label="fieldAriaLabel"
    ></v-autocomplete>

    <v-select
      v-else-if="itemMeta?.options"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :items="getSelectItems(itemMeta)"
      :disabled="itemMeta?.readonly"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      :aria-label="fieldAriaLabel"
    ></v-select>

    <div v-else-if="itemMeta?.editor_mode" class="editor-container">
      <VueMonacoEditor
        :theme="itemMeta?.editor_theme || 'vs-light'"
        :language="itemMeta?.editor_language || 'json'"
        class="config-editor"
        :value="modelValue as OptionalString"
        @update:value="emitUpdate"
      >
      </VueMonacoEditor>
      <v-btn
        v-if="showFullscreenBtn"
        icon
        size="small"
        variant="text"
        color="primary"
        class="editor-fullscreen-btn"
        @click="$emit('open-fullscreen')"
        :title="t('core.common.editor.fullscreen')"
      >
        <v-icon>mdi-fullscreen</v-icon>
      </v-btn>
    </div>

    <v-text-field
      v-else-if="itemMeta?.type === 'string'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :type="stringInputType"
      :append-inner-icon="secretToggleIcon"
      :autocomplete="itemMeta?.secret ? 'new-password' : undefined"
      @click:append-inner="secretVisible = !secretVisible"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      :aria-label="fieldAriaLabel"
    ></v-text-field>

    <div
      v-else-if="itemMeta?.type === 'int' || itemMeta?.type === 'float'"
      class="d-flex align-center gap-3"
    >
      <div v-if="itemMeta?.slider" class="config-slider">
        <span class="config-slider__bound config-slider__bound--start">
          {{ itemMeta?.slider?.min ?? 0 }}
        </span>

        <v-slider
          :model-value="
            toNumber((numericTemp ?? modelValue) as number | string)
          "
          @update:model-value="
            (val) => {
              numericTemp = val;
              emitUpdate(toNumber(val));
            }
          "
          @end="numericTemp = null"
          :min="itemMeta?.slider?.min ?? 0"
          :max="itemMeta?.slider?.max ?? 100"
          :step="itemMeta?.slider?.step ?? 1"
          color="primary"
          density="compact"
          hide-details
          class="config-slider__input"
          :aria-label="fieldAriaLabel"
        ></v-slider>

        <span class="config-slider__bound config-slider__bound--end">
          {{ itemMeta?.slider?.max ?? 100 }}
        </span>
      </div>

      <v-text-field
        :model-value="numericTemp ?? modelValue"
        @update:model-value="(val) => (numericTemp = val)"
        @blur="
          () => {
            if (numericTemp != null) {
              emitUpdate(toNumber(numericTemp));
            }
            numericTemp = null;
          }
        "
        density="compact"
        variant="outlined"
        class="config-field config-number-field"
        type="number"
        hide-details
        :aria-label="fieldAriaLabel"
      ></v-text-field>
    </div>

    <v-textarea
      v-else-if="itemMeta?.type === 'text'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      variant="outlined"
      rows="3"
      class="config-field"
      hide-details
      :aria-label="fieldAriaLabel"
    ></v-textarea>

    <v-switch
      v-else-if="itemMeta?.type === 'bool'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      color="primary"
      inset
      density="compact"
      hide-details
      :aria-label="fieldAriaLabel"
    ></v-switch>

    <FileConfigItem
      v-else-if="itemMeta?.type === 'file'"
      :model-value="modelValue as OptionalStringArray"
      :item-meta="itemMeta"
      :plugin-name="pluginName"
      :config-key="configKey"
      @update:model-value="emitUpdate"
      class="config-field"
    />

    <ListConfigItem
      v-else-if="itemMeta?.type === 'list'"
      :model-value="modelValue as OptionalStringArray"
      @update:model-value="emitUpdate"
      :secret="Boolean(itemMeta?.secret)"
      class="config-field"
    />

    <ObjectEditor
      v-else-if="itemMeta?.type === 'dict'"
      :model-value="modelValue as Record<string, unknown>"
      :item-meta="itemMeta"
      :plugin-name="pluginName"
      :plugin-i18n="pluginI18n"
      :config-key="configKey"
      @update:model-value="emitUpdate"
      class="config-field"
    />

    <v-text-field
      v-else
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :type="stringInputType"
      :append-inner-icon="secretToggleIcon"
      :autocomplete="itemMeta?.secret ? 'new-password' : undefined"
      @click:append-inner="secretVisible = !secretVisible"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      :aria-label="fieldAriaLabel"
    ></v-text-field>
  </div>
</template>

<script setup lang="ts">
import { LazyMonacoEditor as VueMonacoEditor } from './LazyMonacoEditor';
import ListConfigItem from './ListConfigItem.vue';
import FileConfigItem from './FileConfigItem.vue';
import ObjectEditor from './ObjectEditor.vue';
import ProviderSelector from './ProviderSelector.vue';
import SenderSelector from './SenderSelector.vue';
import UmoSelector from './UmoSelector.vue';
import PromptSelector from './PromptSelector.vue';
import KnowledgeBaseSelector from './KnowledgeBaseSelector.vue';
import PluginSetSelector from './PluginSetSelector.vue';
import PluginLoopSelector from './PluginLoopSelector.vue';
import CapabilityLoopSelector from './CapabilityLoopSelector.vue';
import CodingAgentsEditor from './CodingAgentsEditor.vue';
import T2ITemplateEditor from './T2ITemplateEditor.vue';
import DashboardTotpManager from './DashboardTotpManager.vue';
import LocalPermissionMatrix from './LocalPermissionMatrix.vue';
import { computed, ref } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { usePluginI18n } from '@/utils/pluginI18n';

interface SliderMeta {
  min?: number;
  max?: number;
  step?: number;
}

interface TemplateSchemaEntry {
  type?: string;
  slider?: SliderMeta;
}

interface ConfigItemMeta {
  type?: string;
  _special?: string;
  options?: unknown[];
  render_type?: string;
  labels?: string | string[];
  subtitles?: string | string[];
  readonly?: boolean;
  editor_mode?: boolean;
  editor_theme?: string;
  editor_language?: string;
  secret?: boolean;
  slider?: SliderMeta;
  template_schema?: Record<string, TemplateSchemaEntry>;
  runner_defaults?: Record<string, unknown>;
  description?: string;
  hint?: string;
  file_types?: string[];
  [key: string]: unknown;
}

interface Props {
  modelValue?:
    string | number | boolean | unknown[] | Record<string, unknown> | null;
  itemMeta?: ConfigItemMeta | null;
  pluginName?: string;
  pluginI18n?: Record<string, unknown>;
  configKey?: string;
  loading?: boolean;
  showFullscreenBtn?: boolean;
  configRoot?: Record<string, unknown> | null;
}

type ProviderSelectorValue = string | string[];
type OptionalString = string | undefined;
type OptionalStringArray = string[] | undefined;
type OptionalUnknownArray = unknown[] | null | undefined;
type OptionalRecord = Record<string, unknown> | undefined;

const numericTemp = ref<number | string | null>(null);
const listSearchText = ref('');
const secretVisible = ref(false);

const props = withDefaults(defineProps<Props>(), {
  modelValue: null,
  itemMeta: null,
  pluginName: '',
  pluginI18n: () => ({}),
  configKey: '',
  loading: false,
  showFullscreenBtn: false,
  configRoot: null,
});

const emit = defineEmits([
  'update:modelValue',
  'get-embedding-dim',
  'open-fullscreen',
]);
const { t } = useI18n();
const { getRaw } = useModuleI18n('features/config-metadata');
const { configValue } = usePluginI18n();

function emitUpdate(val: unknown): void {
  val = validateNumericConfig(props.itemMeta?.type, val);
  const runnerDefaults = props.itemMeta?.runner_defaults;
  if (
    props.itemMeta?._special === 'agent_runner_type' &&
    props.configRoot?.agent_runner &&
    runnerDefaults?.[String(val)]
  ) {
    const agentRunner = props.configRoot.agent_runner as Record<
      string,
      unknown
    >;
    agentRunner.config = JSON.parse(
      JSON.stringify(runnerDefaults[String(val)]),
    );
  }
  emit('update:modelValue', val);
}

const listSelectItems = computed(() =>
  props.itemMeta?.type === 'list' && props.itemMeta?.options
    ? getSelectItems(props.itemMeta)
    : [],
);

const stringInputType = computed(() =>
  props.itemMeta?.secret && !secretVisible.value ? 'password' : 'text',
);
const secretToggleIcon = computed(() => {
  if (!props.itemMeta?.secret) return undefined;
  return secretVisible.value ? 'mdi-eye-off-outline' : 'mdi-eye-outline';
});

const fieldAriaLabel = computed(
  () => props.itemMeta?.description || props.itemMeta?.hint || '',
);

function toNumber(val: number | string): number {
  const n = parseFloat(String(val));
  return isNaN(n) ? 0 : n;
}

function validateNumericConfig(modelType: unknown, rawValue: unknown): unknown {
  if (modelType === 'int' || modelType === 'float') {
    // 如果有滑动条定义，应用边界限制
    const slider = props.itemMeta?.slider;
    if (slider) {
      const min = slider.min ?? 0;
      const max = slider.max ?? 100;
      return Math.max(min, Math.min(max, Number(rawValue)));
    }
    return rawValue;
  } else if (modelType === 'dict') {
    const dict = rawValue as Record<string, unknown>;
    Object.entries(dict).forEach(([key, value]) => {
      const templatesSchema = props.itemMeta?.template_schema;
      const templateType = templatesSchema?.[key]?.type;
      const templateSlider = templatesSchema?.[key]?.slider;
      if (
        (templateType === 'int' || templateType === 'float') &&
        templateSlider
      ) {
        const min = templateSlider.min ?? 0;
        const max = templateSlider.max ?? 100;
        dict[key] = Math.max(min, Math.min(max, Number(value)));
      }
    });
    return rawValue;
  }
  return rawValue;
}

function getLabel(
  itemMeta: ConfigItemMeta | undefined,
  index: number,
  option: unknown,
): string {
  const labels = getTranslatedLabels(itemMeta);
  return labels?.[index] || (option as string);
}

function getPluginI18nList(attr: 'labels' | 'subtitles'): string[] | null {
  if (
    !props.pluginName ||
    !props.configKey ||
    !props.pluginI18n ||
    Object.keys(props.pluginI18n).length === 0
  ) {
    return null;
  }
  const value = configValue(props.pluginI18n, props.configKey, attr);
  return Array.isArray(value) && value.length > 0 ? (value as string[]) : null;
}

function getTranslatedLabels(itemMeta?: ConfigItemMeta): string[] | null {
  const translatedLabels = getPluginI18nList('labels');
  if (translatedLabels) {
    return translatedLabels;
  }
  if (!itemMeta?.labels) return null;
  if (typeof itemMeta.labels === 'string') {
    const translatedLabels = getRaw(itemMeta.labels);
    if (Array.isArray(translatedLabels)) {
      return translatedLabels;
    }
  }
  if (Array.isArray(itemMeta.labels)) {
    return itemMeta.labels;
  }
  return null;
}

function getTranslatedSubtitles(itemMeta?: ConfigItemMeta): string[] | null {
  const translatedSubtitles = getPluginI18nList('subtitles');
  if (translatedSubtitles) {
    return translatedSubtitles;
  }
  if (!itemMeta?.subtitles) return null;
  if (typeof itemMeta.subtitles === 'string') {
    const translatedSubtitles = getRaw(itemMeta.subtitles);
    if (Array.isArray(translatedSubtitles)) {
      return translatedSubtitles;
    }
  }
  if (Array.isArray(itemMeta.subtitles)) {
    return itemMeta.subtitles;
  }
  return null;
}

function getSelectItems(itemMeta?: ConfigItemMeta): unknown[] {
  const labels = getTranslatedLabels(itemMeta);
  const subtitles = getTranslatedSubtitles(itemMeta);
  if ((labels || subtitles) && itemMeta?.options) {
    return itemMeta.options.map((value, index) => ({
      title: labels?.[index] || value,
      value,
      props: {
        subtitle: subtitles?.[index] || undefined,
      },
    }));
  }
  return itemMeta?.options || [];
}
</script>

<style lang="scss" scoped>
@use './config-editor' as config-editor;

@include config-editor.config-editor-shared;

.config-editor {
  min-height: 100px;
  flex-grow: 1;
  border: 1px solid rgb(var(--v-theme-outline-variant));
}

.config-slider {
  display: flex;
  flex: 3;
  align-items: center;
  gap: 8px;
}

.config-slider__bound {
  min-width: 5px;
}

.config-slider__bound--start {
  text-align: right;
}

.config-slider__bound--end {
  text-align: left;
}

.config-slider__input {
  flex: 1;
}

.config-number-field {
  flex: 2;
}

.checkbox-group {
  gap: 6px 12px;
}

.config-checkbox {
  margin-right: 0;
}

.config-checkbox :deep(.v-selection-control) {
  min-height: 28px;
}

.config-checkbox :deep(.v-selection-control__wrapper) {
  width: 18px;
  height: 18px;
}

.config-checkbox :deep(.v-icon) {
  font-size: 18px;
}

.config-checkbox :deep(.v-label) {
  font-size: 0.9rem;
}

:deep(.v-field__input) {
  font-size: 14px;
}

:deep(.config-field input[type='number']::-webkit-inner-spin-button),
:deep(.config-field input[type='number']::-webkit-outer-spin-button) {
  -webkit-appearance: none;
}

:deep(.config-field input[type='number']) {
  -moz-appearance: textfield;
}
</style>

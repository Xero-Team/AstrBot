import { computed, ref, type Ref } from 'vue';
import { providerApi } from '@/api/v1';
import { resolveErrorMessage } from '@/utils/errorUtils';
import {
  runProviderMutationWithStepUp,
  type RequestDashboardStepUp,
} from '@/utils/stepUp';

interface ProviderSourceRef {
  id?: string;
  type?: string;
}

interface ProviderConfigSchema {
  provider?: {
    items?: Record<string, { invisible?: boolean } & Record<string, unknown>>;
  };
  [key: string]: unknown;
}

interface ProviderEditData {
  id: string;
  model?: string;
  provider_source_id?: string;
  [key: string]: unknown;
}

interface UseProviderModelConfigDialogOptions {
  selectedProviderSource: Ref<ProviderSourceRef | null>;
  configSchema: Ref<ProviderConfigSchema>;
  buildModelProviderConfig?: (
    modelId: string,
  ) => ProviderEditData | null | undefined;
  modelAlreadyConfigured?: (modelId: string) => boolean;
  loadConfig: () => Promise<void> | void;
  tm: (key: string, params?: Record<string, string | number>) => string;
  showMessage: (message: string, color?: string) => void;
  requestStepUp?: RequestDashboardStepUp;
}

// Quick-add templates for `custom_extra_body` on Gemini providers. They use the
// Gemini SDK parameter names (`max_output_tokens` instead of OpenAI's
// `max_tokens`) and drop presets the Gemini SDK rejects, such as
// `reasoning_effort`. Any other parameter can still be added by key.
//
// Labels reuse the `custom_extra_body` config-metadata keys so the dialog stays
// localized instead of embedding hard-coded Chinese text in this module.
const GEMINI_EXTRA_BODY_I18N_PREFIX =
  'provider_group.provider.custom_extra_body.template_schema';

function geminiTemplateLabels(key: string) {
  return {
    name: `${GEMINI_EXTRA_BODY_I18N_PREFIX}.${key}.name`,
    description: `${GEMINI_EXTRA_BODY_I18N_PREFIX}.${key}.description`,
    hint: `${GEMINI_EXTRA_BODY_I18N_PREFIX}.${key}.hint`,
  };
}

const GEMINI_EXTRA_BODY_TEMPLATE = {
  temperature: {
    ...geminiTemplateLabels('temperature'),
    type: 'float',
    default: 1.0,
    slider: { min: 0, max: 2, step: 0.1 },
  },
  top_p: {
    ...geminiTemplateLabels('top_p'),
    type: 'float',
    default: 1.0,
    slider: { min: 0, max: 1, step: 0.01 },
  },
  max_output_tokens: {
    ...geminiTemplateLabels('max_output_tokens'),
    type: 'int',
    default: 8192,
  },
};

export function useProviderModelConfigDialog(
  options: UseProviderModelConfigDialogOptions,
) {
  const {
    selectedProviderSource,
    configSchema,
    buildModelProviderConfig,
    modelAlreadyConfigured,
    loadConfig,
    tm,
    showMessage,
    requestStepUp,
  } = options;

  const showProviderEditDialog = ref(false);
  const providerEditData = ref<ProviderEditData | null>(null);
  const providerEditOriginalId = ref('');
  const providerEditMode = ref<'add' | 'edit'>('edit');
  const savingProviders = ref<string[]>([]);

  const providerModelConfigSchema = computed(() => {
    if (!configSchema.value?.provider?.items) {
      return configSchema.value;
    }

    const schema = JSON.parse(JSON.stringify(configSchema.value));
    const sourceType = selectedProviderSource.value?.type;
    const hiddenKeys = ['id', 'model'];

    const geminiExtraBody = schema.provider?.items?.custom_extra_body as
      { template_schema?: Record<string, unknown> } | undefined;
    if (sourceType === 'googlegenai_chat_completion' && geminiExtraBody) {
      // Replace the OpenAI-oriented presets with Gemini-native parameters.
      geminiExtraBody.template_schema = GEMINI_EXTRA_BODY_TEMPLATE;
    }

    for (const key of hiddenKeys) {
      if (schema.provider.items[key]) {
        schema.provider.items[key].invisible = true;
      }
    }
    return schema;
  });

  const providerEditDialogTitle = computed(() => {
    const actionTitle =
      providerEditMode.value === 'add'
        ? tm('dialogs.config.addTitle')
        : tm('dialogs.config.editTitle');
    const providerId = providerEditData.value?.id;
    return providerId ? `${actionTitle} ${providerId}` : actionTitle;
  });

  function openProviderEdit(provider: ProviderEditData) {
    const editableProvider = JSON.parse(JSON.stringify(provider));
    if (editableProvider.provider_source_id) {
      delete editableProvider.reasoning;
    }
    providerEditData.value = editableProvider;
    providerEditOriginalId.value = provider.id;
    providerEditMode.value = 'edit';
    showProviderEditDialog.value = true;
  }

  function openModelAddDialog(modelId: string) {
    if (!selectedProviderSource.value) {
      showMessage(tm('providerSources.selectHint'), 'error');
      return;
    }
    if (!modelId) return;
    if (modelAlreadyConfigured?.(modelId)) {
      showMessage(tm('models.manualModelExists'), 'error');
      return;
    }

    const newProviderConfig = buildModelProviderConfig?.(modelId);
    if (!newProviderConfig) return;

    providerEditData.value = newProviderConfig;
    providerEditOriginalId.value = '';
    providerEditMode.value = 'add';
    showProviderEditDialog.value = true;
  }

  async function saveEditedProvider() {
    if (!providerEditData.value) return;

    savingProviders.value.push(providerEditData.value.id);
    try {
      const isAdding = providerEditMode.value === 'add';
      const sourceId =
        providerEditData.value.provider_source_id ||
        selectedProviderSource.value?.id;
      if (isAdding && !sourceId) {
        throw new Error(tm('providerSources.selectHint'));
      }
      const providerConfig = providerEditData.value;
      const providerId = providerEditOriginalId.value || providerConfig.id;
      const res = await runProviderMutationWithStepUp(
        (stepUp) =>
          isAdding
            ? providerApi.createInSource(
                sourceId as string,
                providerConfig,
                stepUp,
              )
            : providerApi.update(providerId, providerConfig, stepUp),
        providerId || String(sourceId),
        requestStepUp,
      );
      if (!res) return;

      if (res.data.status === 'error') {
        throw new Error(res.data.message || tm('providerSources.saveError'));
      }

      showMessage(
        res.data.message ||
          (isAdding
            ? tm('models.addSuccess', {
                model: providerEditData.value.model ?? '',
              })
            : tm('providerSources.saveSuccess')),
      );
      showProviderEditDialog.value = false;
      await loadConfig();
    } catch (err) {
      showMessage(
        resolveErrorMessage(err, tm('providerSources.saveError')),
        'error',
      );
    } finally {
      savingProviders.value = savingProviders.value.filter(
        (id) => id !== providerEditData.value?.id,
      );
    }
  }

  return {
    showProviderEditDialog,
    providerEditData,
    savingProviders,
    providerModelConfigSchema,
    providerEditDialogTitle,
    openProviderEdit,
    openModelAddDialog,
    saveEditedProvider,
  };
}

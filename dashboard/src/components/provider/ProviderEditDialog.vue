<template>
  <v-dialog
    :model-value="modelValue"
    width="800"
    scrollable
    :aria-label="title"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="app-dialog provider-form-dialog__card" :title="title">
      <v-card-text class="py-4 provider-form-dialog__content config-form">
        <AstrBotConfig
          v-if="providerEditData"
          :iterable="providerEditData"
          :metadata="providerModelConfigSchema"
          metadata-key="provider"
          :is-editing="true"
        />
      </v-card-text>
      <v-card-actions class="pa-4 provider-form-dialog__actions">
        <v-spacer></v-spacer>
        <v-btn
          variant="text"
          :disabled="isSaving"
          @click="emit('update:modelValue', false)"
        >
          {{ tm('dialogs.config.cancel') }}
        </v-btn>
        <v-btn color="primary" :loading="isSaving" @click="emit('save')">
          {{ tm('dialogs.config.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, type PropType } from 'vue';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';

interface ProviderEditData {
  id?: string;
  [key: string]: unknown;
}

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  providerEditData: {
    type: Object as PropType<ProviderEditData | null>,
    default: null,
  },
  providerModelConfigSchema: {
    type: Object as PropType<Record<string, unknown>>,
    default: () => ({}),
  },
  savingProviders: {
    type: Array as PropType<string[]>,
    default: () => [],
  },
  title: {
    type: String,
    default: '',
  },
  tm: {
    type: Function as PropType<
      (key: string, params?: Record<string, string | number>) => string
    >,
    required: true,
  },
});

const emit = defineEmits(['update:modelValue', 'save']);

const isSaving = computed(() =>
  props.savingProviders.includes(props.providerEditData?.id ?? ''),
);
</script>

<style scoped>
.provider-form-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.provider-form-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.provider-form-dialog__actions {
  flex-shrink: 0;
}
</style>

<style scoped src="@/styles/config-form.css"></style>

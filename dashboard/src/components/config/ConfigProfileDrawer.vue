<script setup lang="ts">
import { computed, ref } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import ConfigPage from '@/views/ConfigPage.vue';

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    configId?: string;
  }>(),
  {
    modelValue: false,
    configId: '',
  },
);

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();
const { tm } = useModuleI18n('core/shared');

interface ConfigPageExposed {
  requestClose(): Promise<boolean>;
}

const open = computed(() => props.modelValue);
const configPage = ref<ConfigPageExposed | null>(null);
const closePending = ref(false);

async function requestClose() {
  if (closePending.value) {
    return;
  }
  closePending.value = true;
  try {
    if (configPage.value && !(await configPage.value.requestClose())) {
      return;
    }
    emit('update:modelValue', false);
  } finally {
    closePending.value = false;
  }
}

function handleOverlayModelUpdate(value: boolean) {
  if (value) {
    emit('update:modelValue', true);
    return;
  }
  void requestClose();
}
</script>

<template>
  <v-overlay
    :model-value="open"
    class="config-profile-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @update:model-value="handleOverlayModelUpdate"
  >
    <v-card class="app-dialog config-profile-drawer-card">
      <div class="config-profile-drawer-header">
        <span class="text-h6">{{ tm('configProfileDrawer.title') }}</span>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          :aria-label="tm('configProfileDrawer.close')"
          @click="requestClose"
        />
      </div>
      <v-divider />
      <div class="config-profile-drawer-content">
        <ConfigPage
          v-if="open && configId"
          ref="configPage"
          :initial-config-id="configId"
        />
      </div>
    </v-card>
  </v-overlay>
</template>

<style scoped>
.config-profile-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.config-profile-drawer-card {
  display: flex;
  width: clamp(320px, 60vw, 820px);
  height: calc(100dvh - 32px);
  flex-direction: column;
  margin: 16px;
}

.config-profile-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--astrbot-space-4) var(--astrbot-space-6) var(--astrbot-space-3);
}

.config-profile-drawer-content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: var(--astrbot-space-4) var(--astrbot-space-4) var(--astrbot-space-6);
}

.config-profile-drawer-content :deep(.config-panel) {
  width: 100%;
  max-width: 100%;
}
</style>

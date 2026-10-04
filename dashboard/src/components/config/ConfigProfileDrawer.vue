<script setup lang="ts">
import { computed } from 'vue';
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

const open = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});
</script>

<template>
  <v-overlay
    v-model="open"
    class="config-profile-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="open = false"
  >
    <v-card class="app-dialog config-profile-drawer-card">
      <div class="config-profile-drawer-header">
        <span class="text-h6">{{ tm('configProfileDrawer.title') }}</span>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          :aria-label="tm('configProfileDrawer.close')"
          @click="open = false"
        />
      </div>
      <v-divider />
      <div class="config-profile-drawer-content">
        <ConfigPage v-if="open && configId" :initial-config-id="configId" />
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
  overflow-y: auto;
  padding: var(--astrbot-space-4) var(--astrbot-space-4) var(--astrbot-space-6);
}
</style>

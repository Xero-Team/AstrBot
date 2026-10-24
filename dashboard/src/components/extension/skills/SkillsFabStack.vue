<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';
const emit = defineEmits<{
  (e: 'refresh'): void;
  (e: 'upload'): void;
}>();

const { tm } = useModuleI18n('features/extension');
</script>

<template>
  <div class="skills-fab-stack">
    <v-tooltip :text="tm('skills.refresh')" location="left">
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          color="primary"
          icon="mdi-refresh"
          size="x-large"
          variant="elevated"
          class="skills-fab"
          :aria-label="tm('skills.refresh')"
          @click="emit('refresh')"
        />
      </template>
    </v-tooltip>
    <v-tooltip :text="tm('skills.upload')" location="left">
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          color="primary"
          icon="mdi-upload"
          size="x-large"
          variant="elevated"
          class="skills-fab"
          :aria-label="tm('skills.upload')"
          @click="emit('upload')"
        />
      </template>
    </v-tooltip>
  </div>
</template>

<style scoped>
.skills-fab-stack {
  align-items: center;
  bottom: 52px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: fixed;
  right: 52px;
  z-index: 10000;
}

.skills-fab {
  border-radius: 16px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.skills-fab:hover {
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
  transform: translateY(-4px) scale(1.05);
}
</style>

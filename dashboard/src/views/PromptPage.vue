<template>
  <div class="prompt-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row class="d-flex justify-space-between align-center py-3 pb-6">
        <div>
          <h1 class="text-h2 mb-1 d-flex align-center">
            {{ t('core.navigation.prompt') }}
            <ConfigDocsLink docs="use/prompt.html" />
          </h1>
          <p class="text-body-2 text-medium-emphasis mb-0">
            {{ tm('page.description') }}
          </p>
        </div>
      </v-row>

      <!-- 主容器组件 -->
      <PromptManager />
    </v-container>
  </div>
</template>

<script setup lang="ts">
import ConfigDocsLink from '@/components/shared/ConfigDocsLink.vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { PromptManager } from '@/views/prompt';

const { t } = useI18n();
const { tm } = useModuleI18n('features/prompt');
</script>

<style scoped>
.prompt-page {
  margin: 0 auto;
  max-width: 1400px;
  padding: 24px;
  width: 100%;
}

@media (max-width: 768px) {
  .prompt-page {
    padding: 16px;
  }
}
</style>

<template>
  <BaseFolderBreadcrumb
    :breadcrumb-path="breadcrumbPath"
    :current-folder-id="currentFolderId"
    :root-folder-name="rootName"
    class="folder-breadcrumb pa-0"
    @navigate="handleClick"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { storeToRefs } from 'pinia';
import BaseFolderBreadcrumb from '@/components/folder/BaseFolderBreadcrumb.vue';

const { tm } = useModuleI18n('features/persona');
const personaStore = usePersonaStore();
const { breadcrumbPath, currentFolderId } = storeToRefs(personaStore);

const rootName = computed(() => tm('folder.rootFolder'));

function handleClick(folderId: string | null) {
  void personaStore.navigateToFolder(folderId);
}
</script>

<style scoped>
.folder-breadcrumb {
  font-size: 14px;
}
</style>

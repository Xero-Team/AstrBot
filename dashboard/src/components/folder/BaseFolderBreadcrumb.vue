<template>
  <v-breadcrumbs :items="computedItems" class="base-folder-breadcrumb pa-0">
    <template #prepend>
      <v-icon size="small" class="mr-1">mdi-folder-outline</v-icon>
    </template>
    <template #item="{ item }">
      <v-breadcrumbs-item
        :disabled="toBreadcrumbItem(item).disabled"
        :class="{ 'breadcrumb-link': !toBreadcrumbItem(item).disabled }"
        @click="
          !toBreadcrumbItem(item).disabled &&
          handleClick(toBreadcrumbItem(item).folderId)
        "
      >
        <v-icon v-if="toBreadcrumbItem(item).isRoot" size="small" class="mr-1"
          >mdi-home</v-icon
        >
        {{ toBreadcrumbItem(item).title }}
      </v-breadcrumbs-item>
    </template>
    <template #divider>
      <v-icon size="small">mdi-chevron-right</v-icon>
    </template>
  </v-breadcrumbs>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { BreadcrumbItem, FolderTreeNode } from './types';

const props = withDefaults(
  defineProps<{
    breadcrumbPath: FolderTreeNode[];
    currentFolderId?: string | null;
    rootFolderName?: string;
  }>(),
  {
    currentFolderId: null,
    rootFolderName: '根目录',
  },
);

const emit = defineEmits<{
  navigate: [folderId: string | null];
}>();

const computedItems = computed<BreadcrumbItem[]>(() => {
  const items: BreadcrumbItem[] = [
    {
      title: props.rootFolderName,
      folderId: null,
      disabled: props.currentFolderId === null,
      isRoot: true,
    },
  ];

  props.breadcrumbPath.forEach((folder, index) => {
    items.push({
      title: folder.name,
      folderId: folder.folder_id,
      disabled: index === props.breadcrumbPath.length - 1,
      isRoot: false,
    });
  });

  return items;
});

function toBreadcrumbItem(item: unknown): BreadcrumbItem {
  return item as BreadcrumbItem;
}

function handleClick(folderId: string | null) {
  emit('navigate', folderId);
}
</script>

<style scoped>
.base-folder-breadcrumb {
  font-size: 14px;
}

.breadcrumb-link {
  cursor: pointer;
  transition: color 0.2s;
}

.breadcrumb-link:hover {
  color: rgb(var(--v-theme-primary));
}
</style>

<template>
  <BaseFolderCard
    :folder="folder"
    :accept-drop-types="['persona']"
    :labels="{
      open: tm('folder.contextMenu.open'),
      rename: tm('folder.contextMenu.rename'),
      moveTo: tm('folder.contextMenu.moveTo'),
      delete: tm('folder.contextMenu.delete'),
    }"
    @click="emit('click')"
    @contextmenu="emit('contextmenu', $event)"
    @open="emit('open')"
    @rename="emit('rename')"
    @move="emit('move')"
    @delete="emit('delete')"
    @item-dropped="onItemDropped"
  />
</template>

<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';
import BaseFolderCard from '@/components/folder/BaseFolderCard.vue';
import type { DropEventData, Folder } from '@/components/folder/types';

const props = defineProps<{
  folder: Folder;
}>();

const emit = defineEmits<{
  click: [];
  contextmenu: [event: MouseEvent];
  open: [];
  rename: [];
  move: [];
  delete: [];
  'persona-dropped': [
    payload: { persona_id: string; target_folder_id: string | null },
  ];
}>();

const { tm } = useModuleI18n('features/persona');

function onItemDropped(data: DropEventData) {
  if (data.item_type === 'persona') {
    emit('persona-dropped', {
      persona_id: data.item_id,
      target_folder_id: data.target_folder_id ?? props.folder.folder_id,
    });
  }
}
</script>

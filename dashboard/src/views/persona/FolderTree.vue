<template>
  <div class="folder-tree">
    <BaseFolderTree
      :folder-tree="folderTree"
      :current-folder-id="currentFolderId"
      :expanded-folder-ids="expandedFolderIds"
      :tree-loading="treeLoading"
      :accept-drop-types="['persona']"
      :labels="{
        searchPlaceholder: tm('folder.searchPlaceholder'),
        rootFolder: tm('folder.rootFolder'),
        noFolders: tm('folder.noFolders'),
        contextMenu: {
          open: tm('folder.contextMenu.open'),
          rename: tm('folder.contextMenu.rename'),
          moveTo: tm('folder.contextMenu.moveTo'),
          delete: tm('folder.contextMenu.delete'),
        },
      }"
      @folder-click="handleFolderClick"
      @rename-folder="onRenameFolder"
      @move-folder="emit('move-folder', $event)"
      @delete-folder="onDeleteFolder"
      @item-dropped="onItemDropped"
      @toggle-expansion="toggleFolderExpansion"
      @set-expansion="handleSetFolderExpansion"
    />

    <!-- 重命名对话框 -->
    <v-dialog v-model="renameDialog.show" max-width="400px" persistent>
      <v-card>
        <v-card-title>{{ tm('folder.renameDialog.title') }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="renameDialog.name"
            :label="tm('folder.form.name')"
            :rules="[(v) => !!v || tm('folder.validation.nameRequired')]"
            variant="outlined"
            density="comfortable"
            autofocus
            @keyup.enter="submitRename"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="renameDialog.show = false">
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="renameDialog.loading"
            :disabled="!renameDialog.name"
            @click="submitRename"
          >
            {{ tm('buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="deleteDialog.show" max-width="450px">
      <v-card>
        <v-card-title class="text-error">
          <v-icon class="mr-2" color="error">mdi-alert</v-icon>
          {{ tm('folder.deleteDialog.title') }}
        </v-card-title>
        <v-card-text>
          <p>
            {{
              tm('folder.deleteDialog.message', {
                name: deleteDialog.folder?.name ?? '',
              })
            }}
          </p>
          <p class="text-warning mt-2">
            <v-icon size="small" class="mr-1">mdi-information</v-icon>
            {{ tm('folder.deleteDialog.warning') }}
          </p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn
            color="error"
            variant="flat"
            :loading="deleteDialog.loading"
            @click="submitDelete"
          >
            {{ tm('buttons.delete') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { storeToRefs } from 'pinia';
import BaseFolderTree from '@/components/folder/BaseFolderTree.vue';
import type { DropEventData, Folder } from '@/components/folder/types';
import { resolveErrorMessage } from '@/utils/errorUtils';

const emit = defineEmits<{
  'move-folder': [folder: Folder];
  error: [message: string];
  success: [message: string];
  'persona-dropped': [
    payload: { persona_id: string; target_folder_id: string | null },
  ];
}>();

const { tm } = useModuleI18n('features/persona');
const personaStore = usePersonaStore();
const { folderTree, currentFolderId, treeLoading, expandedFolderIds } =
  storeToRefs(personaStore);

const renameDialog = reactive<{
  show: boolean;
  folder: Folder | null;
  name: string;
  loading: boolean;
}>({
  show: false,
  folder: null,
  name: '',
  loading: false,
});

const deleteDialog = reactive<{
  show: boolean;
  folder: Folder | null;
  loading: boolean;
}>({
  show: false,
  folder: null,
  loading: false,
});

function handleFolderClick(folderId: string | null) {
  void personaStore.navigateToFolder(folderId);
}

function onRenameFolder(folder: Folder) {
  renameDialog.folder = folder;
  renameDialog.name = folder.name;
  renameDialog.show = true;
}

function onDeleteFolder(folder: Folder) {
  deleteDialog.folder = folder;
  deleteDialog.show = true;
}

function handleSetFolderExpansion(data: {
  folderId: string;
  expanded: boolean;
}) {
  personaStore.setFolderExpansion(data.folderId, data.expanded);
}

function onItemDropped(data: DropEventData) {
  if (data.item_type === 'persona') {
    emit('persona-dropped', {
      persona_id: data.item_id,
      target_folder_id: data.target_folder_id,
    });
  }
}

async function submitRename() {
  if (!renameDialog.name || !renameDialog.folder) {
    return;
  }

  renameDialog.loading = true;
  try {
    await personaStore.updateFolder({
      folder_id: renameDialog.folder.folder_id,
      name: renameDialog.name,
    });
    emit('success', tm('folder.messages.renameSuccess'));
    renameDialog.show = false;
  } catch (error) {
    emit(
      'error',
      resolveErrorMessage(error, tm('folder.messages.renameError')),
    );
  } finally {
    renameDialog.loading = false;
  }
}

async function submitDelete() {
  if (!deleteDialog.folder) {
    return;
  }

  deleteDialog.loading = true;
  try {
    await personaStore.deleteFolder(deleteDialog.folder.folder_id);
    emit('success', tm('folder.messages.deleteSuccess'));
    deleteDialog.show = false;
  } catch (error) {
    emit(
      'error',
      resolveErrorMessage(error, tm('folder.messages.deleteError')),
    );
  } finally {
    deleteDialog.loading = false;
  }
}

const { toggleFolderExpansion } = personaStore;
</script>

<style scoped>
.folder-tree {
  height: 100%;
  display: flex;
  flex-direction: column;
}
</style>

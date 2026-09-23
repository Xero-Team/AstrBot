<template>
  <div class="prompt-manager">
    <!-- 移动端顶部导航 -->
    <div class="mobile-nav d-md-none mb-4">
      <FolderBreadcrumb />
    </div>

    <div class="manager-layout">
      <!-- 左侧边栏 - 仅桌面端显示 -->
      <div class="sidebar d-none d-md-block">
        <div
          class="sidebar-header d-flex justify-space-between align-center mb-3"
        >
          <h3 class="text-h6">{{ tm('folder.sidebarTitle') }}</h3>
          <v-btn
            icon="mdi-folder-plus"
            variant="text"
            size="small"
            :title="tm('folder.createButton')"
            @click="showCreateFolderDialog = true"
          />
        </div>
        <FolderTree
          @move-folder="openMoveFolderDialog"
          @success="showSuccess"
          @error="showError"
          @prompt-dropped="handlePromptDropped"
        />
      </div>

      <!-- 主内容区 -->
      <div class="main-content">
        <!-- 顶部工具栏 -->
        <div
          class="toolbar d-flex flex-wrap justify-space-between align-center mb-4 ga-2"
        >
          <!-- 面包屑 - 仅桌面端显示 -->
          <div class="d-none d-md-block">
            <FolderBreadcrumb />
          </div>

          <!-- 操作按钮组 -->
          <div class="d-flex ga-2">
            <v-btn
              variant="outlined"
              prepend-icon="mdi-upload"
              rounded="md"
              @click="triggerImport"
            >
              {{ tm('buttons.import') }}
            </v-btn>
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-plus"
              rounded="md"
              @click="openCreatePromptDialog"
            >
              {{ tm('buttons.create') }}
            </v-btn>
            <input
              ref="importFileInput"
              type="file"
              accept="application/json,.json"
              hidden
              @change="handleImportFile"
            />
            <v-btn
              variant="outlined"
              prepend-icon="mdi-folder-plus"
              rounded="md"
              @click="showCreateFolderDialog = true"
            >
              {{ tm('folder.createButton') }}
            </v-btn>
          </div>
        </div>

        <!-- 加载状态 - 只有加载超过阈值才显示骨架屏 -->
        <v-fade-transition>
          <div v-if="showSkeleton" class="loading-container">
            <v-row>
              <v-col v-for="n in 6" :key="n" cols="12" sm="6" lg="6" xl="4">
                <v-skeleton-loader type="card" rounded="md" />
              </v-col>
            </v-row>
          </div>
        </v-fade-transition>

        <!-- 内容区域 -->
        <div v-if="!loading">
          <!-- 子文件夹区域 -->
          <div v-if="currentFolders.length > 0" class="folders-section mb-6">
            <h3 class="text-subtitle-1 font-weight-medium mb-3">
              <v-icon size="small" class="mr-1">mdi-folder</v-icon>
              {{ tm('folder.foldersTitle') }} ({{ currentFolders.length }})
            </h3>
            <v-row>
              <v-col
                v-for="folder in currentFolders"
                :key="folder.folder_id"
                cols="12"
                sm="6"
                lg="6"
                xl="4"
              >
                <FolderCard
                  :folder="folder"
                  @click="promptStore.navigateToFolder(folder.folder_id)"
                  @open="promptStore.navigateToFolder(folder.folder_id)"
                  @rename="openRenameFolderDialog(folder)"
                  @move="openMoveFolderDialog(folder)"
                  @delete="confirmDeleteFolder(folder)"
                  @prompt-dropped="handlePromptDropped"
                />
              </v-col>
            </v-row>
          </div>

          <!-- Prompt 区域 -->
          <div v-if="currentPrompts.length > 0" class="prompts-section">
            <h3 class="text-subtitle-1 font-weight-medium mb-3">
              <v-icon size="small" class="mr-1">mdi-account-heart</v-icon>
              {{ tm('prompt.promptsTitle') }} ({{ currentPrompts.length }})
            </h3>
            <v-row>
              <v-col
                v-for="prompt in currentPrompts"
                :key="prompt.prompt_id"
                cols="12"
                sm="6"
                lg="6"
                xl="4"
              >
                <PromptCard
                  :prompt="prompt"
                  @view="viewPrompt(prompt)"
                  @edit="editPrompt(prompt)"
                  @move="openMovePromptDialog(prompt)"
                  @delete="confirmDeletePrompt(prompt)"
                  @export="handlePromptExport"
                />
              </v-col>
            </v-row>
          </div>

          <!-- 空状态 -->
          <div
            v-if="currentFolders.length === 0 && currentPrompts.length === 0"
            class="empty-state"
          >
            <v-card class="text-center pa-8" elevation="0">
              <v-icon size="64" color="on-surface-variant" class="mb-4"
                >mdi-folder-open-outline</v-icon
              >
              <h3 class="text-h5 mb-2">{{ tm('empty.folderEmpty') }}</h3>
              <p class="text-body-1 text-medium-emphasis mb-4">
                {{ tm('empty.folderEmptyDescription') }}
              </p>
              <div class="d-flex justify-center ga-2">
                <v-btn
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-plus"
                  @click="openCreatePromptDialog"
                >
                  {{ tm('buttons.create') }}
                </v-btn>
                <v-btn
                  variant="outlined"
                  prepend-icon="mdi-folder-plus"
                  @click="showCreateFolderDialog = true"
                >
                  {{ tm('folder.createButton') }}
                </v-btn>
              </div>
            </v-card>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑 Prompt 对话框 -->
    <PromptForm
      v-model="showPromptDialog"
      :editing-prompt="editingPrompt ?? undefined"
      :current-folder-id="currentFolderId ?? undefined"
      :current-folder-name="currentFolderName ?? undefined"
      @saved="handlePromptSaved"
      @deleted="handlePromptDeleted"
      @error="showError"
    />

    <!-- 查看 Prompt 详情对话框 -->
    <v-dialog v-model="showViewDialog" max-width="700px" scrollable>
      <v-card v-if="viewingPrompt" class="prompt-preview-dialog__card">
        <v-card-title class="d-flex justify-space-between align-center">
          <span class="text-h5">{{ viewingPrompt.prompt_id }}</span>
          <div class="d-flex align-center ga-1">
            <v-btn
              color="primary"
              variant="tonal"
              size="small"
              prepend-icon="mdi-pencil"
              @click="openEditFromViewDialog"
            >
              {{ tm('buttons.edit') }}
            </v-btn>
            <v-btn
              icon="mdi-close"
              variant="text"
              @click="showViewDialog = false"
            />
          </div>
        </v-card-title>

        <v-card-text class="prompt-preview-dialog__content">
          <div class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.systemPrompt') }}</h4>
            <pre class="system-prompt-content">{{
              viewingPrompt.system_prompt
            }}</pre>
          </div>

          <div v-if="viewingPrompt.custom_error_message" class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.customErrorMessage') }}</h4>
            <pre class="system-prompt-content">{{
              viewingPrompt.custom_error_message
            }}</pre>
          </div>

          <div
            v-if="
              viewingPrompt.begin_dialogs &&
              viewingPrompt.begin_dialogs.length > 0
            "
            class="mb-4"
          >
            <h4 class="text-h6 mb-2">{{ tm('form.presetDialogs') }}</h4>
            <div
              v-for="(dialog, index) in viewingPrompt.begin_dialogs"
              :key="index"
              class="mb-2"
            >
              <v-chip
                :color="index % 2 === 0 ? 'primary' : 'secondary'"
                variant="tonal"
                size="small"
                class="mb-1"
              >
                {{
                  index % 2 === 0
                    ? tm('form.userMessage')
                    : tm('form.assistantMessage')
                }}
              </v-chip>
              <div class="dialog-content ml-2">{{ dialog }}</div>
            </div>
          </div>

          <div class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.tools') }}</h4>
            <div
              v-if="viewingPrompt.tools === null"
              class="text-body-2 text-medium-emphasis"
            >
              <v-chip
                size="small"
                color="success"
                variant="tonal"
                prepend-icon="mdi-check-all"
              >
                {{ tm('form.allToolsAvailable') }}
              </v-chip>
            </div>
            <div
              v-else-if="viewingPrompt.tools && viewingPrompt.tools.length > 0"
              class="d-flex flex-wrap ga-1"
            >
              <v-chip
                v-for="toolName in viewingPrompt.tools"
                :key="toolName"
                size="small"
                color="primary"
                variant="tonal"
              >
                {{ toolName }}
              </v-chip>
            </div>
            <div v-else class="text-body-2 text-medium-emphasis">
              {{ tm('form.noToolsSelected') }}
            </div>
          </div>

          <div class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.skills') }}</h4>
            <div
              v-if="viewingPrompt.skills === null"
              class="text-body-2 text-medium-emphasis"
            >
              <v-chip
                size="small"
                color="success"
                variant="tonal"
                prepend-icon="mdi-check-all"
              >
                {{ tm('form.allSkillsAvailable') }}
              </v-chip>
            </div>
            <div
              v-else-if="
                viewingPrompt.skills && viewingPrompt.skills.length > 0
              "
              class="d-flex flex-wrap ga-1"
            >
              <v-chip
                v-for="skillName in viewingPrompt.skills"
                :key="skillName"
                size="small"
                color="primary"
                variant="tonal"
              >
                {{ skillName }}
              </v-chip>
            </div>
            <div v-else class="text-body-2 text-medium-emphasis">
              {{ tm('form.noSkillsSelected') }}
            </div>
          </div>

          <div class="text-caption text-medium-emphasis">
            <div>
              {{ tm('labels.createdAt') }}:
              {{ formatDate(viewingPrompt.created_at) }}
            </div>
            <div v-if="viewingPrompt.updated_at">
              {{ tm('labels.updatedAt') }}:
              {{ formatDate(viewingPrompt.updated_at) }}
            </div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 创建文件夹对话框 -->
    <CreateFolderDialog
      v-model="showCreateFolderDialog"
      :parent-folder-id="currentFolderId"
      @created="showSuccess"
      @error="showError"
    />

    <!-- 重命名文件夹对话框 -->
    <v-dialog v-model="showRenameFolderDialog" max-width="400px">
      <v-card>
        <v-card-title>{{ tm('folder.renameDialog.title') }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="renameFolderData.name"
            :label="tm('folder.form.name')"
            :rules="[(v) => !!v || tm('folder.validation.nameRequired')]"
            variant="outlined"
            density="comfortable"
            autofocus
            @keyup.enter="submitRenameFolder"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showRenameFolderDialog = false">
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="renameLoading"
            :disabled="!renameFolderData.name"
            @click="submitRenameFolder"
          >
            {{ tm('buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 移动对话框 -->
    <MoveToFolderDialog
      v-model="showMoveDialog"
      :item-type="moveDialogType"
      :item="moveDialogItem"
      @moved="showSuccess"
      @error="showError"
    />

    <!-- 删除文件夹确认对话框 -->
    <v-dialog v-model="showDeleteFolderDialog" max-width="450px">
      <v-card>
        <v-card-title class="text-error">
          <v-icon class="mr-2" color="error">mdi-alert</v-icon>
          {{ tm('folder.deleteDialog.title') }}
        </v-card-title>
        <v-card-text>
          <p>
            {{
              tm('folder.deleteDialog.message', {
                name: deleteFolderData?.name ?? '',
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
          <v-btn variant="text" @click="showDeleteFolderDialog = false">
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn
            color="error"
            variant="flat"
            :loading="deleteLoading"
            @click="submitDeleteFolder"
          >
            {{ tm('buttons.delete') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar
      v-model="showMessage"
      :timeout="3000"
      elevation="4"
      :color="messageType"
      location="top"
    >
      {{ message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePromptStore } from '@/stores/promptStore';
import { promptApi } from '@/api/v1';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { storeToRefs } from 'pinia';

import FolderTree from './FolderTree.vue';
import FolderBreadcrumb from './FolderBreadcrumb.vue';
import FolderCard from './FolderCard.vue';
import PromptCard from './PromptCard.vue';
import PromptForm from '@/components/shared/PromptForm.vue';
import CreateFolderDialog from './CreateFolderDialog.vue';
import MoveToFolderDialog from './MoveToFolderDialog.vue';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';

import type { Folder, FolderTreeNode } from '@/components/folder/types';
import type { Prompt as StorePrompt } from '@/stores/promptStore';

type MoveDialogType = 'prompt' | 'folder';
type SnackbarType = 'success' | 'error';

const { tm } = useModuleI18n('features/prompt');
const confirmDialog = useConfirmDialog();
const promptStore = usePromptStore();
const { folderTree, currentFolderId, currentFolders, currentPrompts, loading } =
  storeToRefs(promptStore);

const showPromptDialog = ref(false);
const importFileInput = ref<HTMLInputElement | null>(null);
const showViewDialog = ref(false);
const editingPrompt = ref<StorePrompt | null>(null);
const viewingPrompt = ref<StorePrompt | null>(null);

const showCreateFolderDialog = ref(false);
const showRenameFolderDialog = ref(false);
const showDeleteFolderDialog = ref(false);
const renameFolderData = ref<{ folder: Folder | null; name: string }>({
  folder: null,
  name: '',
});
const deleteFolderData = ref<Folder | null>(null);
const renameLoading = ref(false);
const deleteLoading = ref(false);

const showMoveDialog = ref(false);
const moveDialogType = ref<MoveDialogType>('prompt');
const moveDialogItem = ref<StorePrompt | Folder | null>(null);

const showMessage = ref(false);
const message = ref('');
const messageType = ref<SnackbarType>('success');

const showSkeleton = ref(false);
const skeletonTimer = ref<ReturnType<typeof setTimeout> | null>(null);

const currentFolderName = computed(() => {
  if (!currentFolderId.value) {
    return null;
  }

  const findName = (nodes: FolderTreeNode[], id: string): string | null => {
    for (const node of nodes) {
      if (node.folder_id === id) {
        return node.name;
      }
      if (node.children.length > 0) {
        const found = findName(node.children, id);
        if (found) {
          return found;
        }
      }
    }
    return null;
  };

  return findName(folderTree.value, currentFolderId.value);
});

watch(
  loading,
  (newVal) => {
    if (newVal) {
      skeletonTimer.value = setTimeout(() => {
        if (loading.value) {
          showSkeleton.value = true;
        }
      }, 150);
      return;
    }

    if (skeletonTimer.value) {
      clearTimeout(skeletonTimer.value);
      skeletonTimer.value = null;
    }
    showSkeleton.value = false;
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (skeletonTimer.value) {
    clearTimeout(skeletonTimer.value);
  }
});

onMounted(async () => {
  await initialize();
});

async function initialize() {
  await Promise.all([
    promptStore.loadFolderTree(),
    promptStore.navigateToFolder(null),
  ]);
}

function openCreatePromptDialog() {
  editingPrompt.value = null;
  showPromptDialog.value = true;
}

function handlePromptExport(exportMessage: string, isError: boolean) {
  if (isError) {
    showError(exportMessage);
    return;
  }
  showSuccess(exportMessage);
}

function triggerImport() {
  if (importFileInput.value) {
    importFileInput.value.value = '';
    importFileInput.value.click();
  }
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;

  try {
    const data: unknown = JSON.parse(await file.text());
    if (!data || typeof data !== 'object' || !('system_prompt' in data)) {
      showError(tm('messages.importMissingPrompt'));
      return;
    }
    const imported = data as {
      prompt_id?: unknown;
      system_prompt?: unknown;
      begin_dialogs?: unknown;
    };
    if (typeof imported.system_prompt !== 'string' || !imported.system_prompt) {
      showError(tm('messages.importMissingPrompt'));
      return;
    }

    const response = await promptApi.list();
    const existingIds = new Set(
      response.data.status === 'ok'
        ? (response.data.data || []).map((prompt) => prompt.prompt_id)
        : [],
    );
    const baseId =
      typeof imported.prompt_id === 'string' && imported.prompt_id
        ? imported.prompt_id
        : 'imported_prompt';
    let promptId = baseId;
    let suffix = 1;
    while (existingIds.has(promptId)) {
      promptId = `${baseId}_imported${suffix === 1 ? '' : `_${suffix}`}`;
      suffix += 1;
    }

    const createResponse = await promptApi.create({
      prompt_id: promptId,
      system_prompt: imported.system_prompt,
      begin_dialogs: Array.isArray(imported.begin_dialogs)
        ? imported.begin_dialogs.filter(
            (item): item is string => typeof item === 'string',
          )
        : [],
      tools: null,
      skills: null,
      folder_id: currentFolderId.value,
    });
    if (createResponse.data.status !== 'ok') {
      throw new Error(
        createResponse.data.message || tm('messages.importError'),
      );
    }
    await promptStore.refreshCurrentFolder();
    if (promptId !== baseId) {
      showSuccess(tm('messages.importIdExists', { id: promptId }));
    } else {
      showSuccess(tm('messages.importSuccess'));
    }
  } catch (error) {
    if (error instanceof SyntaxError) {
      showError(tm('messages.importFormatError'));
      return;
    }
    console.error('Failed to import prompt:', error);
    showError(resolveErrorMessage(error, tm('messages.importError')));
  }
}

function editPrompt(prompt: StorePrompt) {
  editingPrompt.value = prompt;
  showPromptDialog.value = true;
}

function viewPrompt(prompt: StorePrompt) {
  viewingPrompt.value = prompt;
  showViewDialog.value = true;
}

function openEditFromViewDialog() {
  if (!viewingPrompt.value) {
    return;
  }
  editingPrompt.value = viewingPrompt.value;
  showViewDialog.value = false;
  showPromptDialog.value = true;
}

function handlePromptSaved(successMessage: string) {
  showSuccess(successMessage);
  void promptStore.refreshCurrentFolder();
}

function handlePromptDeleted(successMessage: string) {
  showSuccess(successMessage);
  void promptStore.refreshCurrentFolder();
}

async function confirmDeletePrompt(prompt: StorePrompt) {
  if (
    !(await askForConfirmationDialog(
      tm('messages.deleteConfirm', { id: prompt.prompt_id }),
      confirmDialog,
    ))
  ) {
    return;
  }

  try {
    await promptStore.deletePrompt(prompt.prompt_id);
    showSuccess(tm('messages.deleteSuccess'));
  } catch (error) {
    showError(resolveErrorMessage(error, tm('messages.deleteError')));
  }
}

function openMovePromptDialog(prompt: StorePrompt) {
  moveDialogType.value = 'prompt';
  moveDialogItem.value = prompt;
  showMoveDialog.value = true;
}

async function handlePromptDropped({
  prompt_id,
  target_folder_id,
}: {
  prompt_id: string;
  target_folder_id: string | null;
}) {
  try {
    await promptStore.movePromptToFolder(prompt_id, target_folder_id);
    showSuccess(tm('prompt.messages.moveSuccess'));
    await promptStore.navigateToFolder(target_folder_id);
  } catch (error) {
    showError(resolveErrorMessage(error, tm('prompt.messages.moveError')));
  }
}

function openRenameFolderDialog(folder: Folder) {
  renameFolderData.value = { folder, name: folder.name };
  showRenameFolderDialog.value = true;
}

async function submitRenameFolder() {
  if (!renameFolderData.value.name || !renameFolderData.value.folder) {
    return;
  }

  renameLoading.value = true;
  try {
    await promptStore.updateFolder({
      folder_id: renameFolderData.value.folder.folder_id,
      name: renameFolderData.value.name,
    });
    showSuccess(tm('folder.messages.renameSuccess'));
    showRenameFolderDialog.value = false;
  } catch (error) {
    showError(resolveErrorMessage(error, tm('folder.messages.renameError')));
  } finally {
    renameLoading.value = false;
  }
}

function openMoveFolderDialog(folder: Folder) {
  moveDialogType.value = 'folder';
  moveDialogItem.value = folder;
  showMoveDialog.value = true;
}

function confirmDeleteFolder(folder: Folder) {
  deleteFolderData.value = folder;
  showDeleteFolderDialog.value = true;
}

async function submitDeleteFolder() {
  if (!deleteFolderData.value) {
    return;
  }

  deleteLoading.value = true;
  try {
    await promptStore.deleteFolder(deleteFolderData.value.folder_id);
    showSuccess(tm('folder.messages.deleteSuccess'));
    showDeleteFolderDialog.value = false;
  } catch (error) {
    showError(resolveErrorMessage(error, tm('folder.messages.deleteError')));
  } finally {
    deleteLoading.value = false;
  }
}

function formatDate(dateString: string | undefined | null): string {
  if (!dateString) {
    return '';
  }
  return new Date(dateString).toLocaleString();
}

function showSuccess(successMessage: string) {
  message.value = successMessage;
  messageType.value = 'success';
  showMessage.value = true;
}

function showError(errorMessage: string) {
  message.value = errorMessage;
  messageType.value = 'error';
  showMessage.value = true;
}
</script>

<style scoped>
.prompt-manager {
  height: 100%;
}

.manager-layout {
  display: flex;
  gap: 24px;
  height: 100%;
}

.sidebar {
  width: 280px;
  flex-shrink: 0;
  padding-right: 16px;
  max-height: calc(100vh - 200px);
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1;
  min-width: 0;
}

.prompt-preview-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 860px);
}

.prompt-preview-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.system-prompt-content {
  max-height: 400px;
  overflow: auto;
  padding: 12px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(var(--v-theme-surface-variant), 0.3);
}

.dialog-content {
  background-color: rgba(var(--v-theme-surface-variant), 0.3);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 960px) {
  .manager-layout {
    flex-direction: column;
  }

  .sidebar {
    display: none;
  }
}
</style>

<template>
  <div class="prompt-selector">
    <BaseFolderItemSelector
      :model-value="modelValue"
      :folder-tree="folderTree"
      :items="currentPrompts"
      :tree-loading="treeLoading"
      :items-loading="itemsLoading"
      :labels="labels"
      :show-create-button="true"
      :show-edit-button="true"
      :default-item="defaultPrompt"
      item-id-field="prompt_id"
      item-name-field="prompt_id"
      @update:model-value="handleUpdate"
      item-description-field="system_prompt"
      :display-value-formatter="formatDisplayValue"
      @navigate="handleNavigate"
      @create="openCreatePrompt"
      @edit="openEditPrompt"
    />

    <!-- 创建/编辑提示词对话框 -->
    <PromptForm
      v-model="showPromptDialog"
      :editing-prompt="editingPrompt ?? undefined"
      :current-folder-id="currentFolderId ?? undefined"
      :current-folder-name="currentFolderName ?? undefined"
      @saved="handlePromptSaved"
      @error="handleError"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { promptApi } from '@/api/v1';
import BaseFolderItemSelector from '@/components/folder/BaseFolderItemSelector.vue';
import PromptForm from './PromptForm.vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import type { FolderTreeNode, SelectableItem } from '@/components/folder/types';

interface PromptApiRecord {
  prompt_id: string;
  system_prompt: string;
  custom_error_message?: string | null;
  folder_id?: string | null;
}

type PromptSelectableItem = SelectableItem & PromptApiRecord;

function isPromptSelectableItem(
  item: SelectableItem,
): item is PromptSelectableItem {
  return (
    typeof item.prompt_id === 'string' && typeof item.system_prompt === 'string'
  );
}

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  buttonText: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['update:modelValue']);
const { t } = useI18n();
const { tm } = useModuleI18n('core.shared');

// 状态
const folderTree = ref<FolderTreeNode[]>([]);
const currentPrompts = ref<PromptSelectableItem[]>([]);
const treeLoading = ref(false);
const itemsLoading = ref(false);
const showPromptDialog = ref(false);
const editingPrompt = ref<PromptSelectableItem | null>(null);
const currentFolderId = ref<string | null>(null);

// 默认提示词
const defaultPrompt: SelectableItem = {
  id: 'default',
  prompt_id: 'default',
  name: tm('promptSelector.defaultPrompt'),
  system_prompt: 'You are a helpful and friendly assistant.',
};

// 递归查找文件夹名称
function findFolderName(
  nodes: FolderTreeNode[],
  folderId: string,
): string | null {
  for (const node of nodes) {
    if (node.folder_id === folderId) {
      return node.name;
    }
    if (node.children && node.children.length > 0) {
      const found = findFolderName(node.children, folderId);
      if (found) return found;
    }
  }
  return null;
}

// 当前文件夹名称
const currentFolderName = computed(() => {
  if (!currentFolderId.value) {
    return null; // 根目录，PromptForm 会使用 tm('form.rootFolder')
  }
  return findFolderName(folderTree.value, currentFolderId.value);
});

// 标签配置
const labels = computed(() => ({
  dialogTitle: tm('promptSelector.dialogTitle'),
  notSelected: tm('promptSelector.notSelected'),
  buttonText: props.buttonText || tm('promptSelector.buttonText'),
  noItems: tm('promptSelector.noPrompts'),
  defaultItem: tm('promptSelector.defaultPrompt'),
  noDescription: tm('promptSelector.noDescription'),
  createButton: tm('promptSelector.createPrompt'),
  editButton: tm('promptSelector.editPrompt') || 'Edit',
  confirmButton: t('core.common.confirm'),
  cancelButton: t('core.common.cancel'),
  rootFolder: tm('promptSelector.rootFolder') || '全部提示词',
  emptyFolder: tm('promptSelector.emptyFolder') || '此文件夹为空',
}));

// 格式化显示值
function formatDisplayValue(value: string): string {
  if (value === 'default') {
    return tm('promptSelector.defaultPrompt');
  }
  return value;
}

// 处理值更新
function handleUpdate(value: string) {
  emit('update:modelValue', value);
}

// 加载文件夹树
async function loadFolderTree() {
  treeLoading.value = true;
  try {
    const response = await promptApi.tree();
    if (response.data.status === 'ok') {
      folderTree.value = response.data.data || [];
    }
  } catch (error) {
    console.error('加载文件夹树失败:', error);
    folderTree.value = [];
  } finally {
    treeLoading.value = false;
  }
}

// 加载指定文件夹的提示词
async function loadPromptsInFolder(folderId: string | null) {
  itemsLoading.value = true;
  try {
    const response = await promptApi.list(folderId);
    if (response.data.status === 'ok') {
      const prompts = Array.isArray(response.data.data)
        ? (response.data.data as PromptApiRecord[])
        : [];
      currentPrompts.value = prompts.map((prompt) => ({
        ...prompt,
        id: prompt.prompt_id,
        name: prompt.prompt_id,
        description: prompt.system_prompt,
      }));
    }
  } catch (error) {
    console.error('加载提示词列表失败:', error);
    currentPrompts.value = [];
  } finally {
    itemsLoading.value = false;
  }
}

// 处理文件夹导航
async function handleNavigate(folderId: string | null) {
  currentFolderId.value = folderId;
  await loadPromptsInFolder(folderId);
}

// 打开创建提示词对话框
function openCreatePrompt() {
  editingPrompt.value = null;
  showPromptDialog.value = true;
}

// 打开编辑提示词对话框
function openEditPrompt(item: SelectableItem) {
  if (!isPromptSelectableItem(item)) {
    return;
  }

  editingPrompt.value = item;
  showPromptDialog.value = true;
}

// 提示词保存成功（创建或编辑）
async function handlePromptSaved(message: string) {
  console.log('提示词保存成功:', message);
  const savedPromptId = editingPrompt.value?.prompt_id || '';
  showPromptDialog.value = false;
  editingPrompt.value = null;
  // 刷新当前文件夹的提示词列表
  await loadPromptsInFolder(currentFolderId.value);
  window.dispatchEvent(
    new CustomEvent('astrbot:prompt-saved', {
      detail: { prompt_id: savedPromptId },
    }),
  );
}

// 错误处理
function handleError(error: string) {
  console.error('创建提示词失败:', error);
}

// 初始化加载文件夹树
onMounted(() => {
  void loadFolderTree();
});
</script>

<style scoped>
/* 样式继承自 BaseFolderItemSelector */
</style>

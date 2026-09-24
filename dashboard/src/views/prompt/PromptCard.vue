<template>
  <v-card
    class="prompt-card"
    :class="{ dragging: isDragging }"
    rounded="md"
    variant="outlined"
    elevation="0"
    draggable="true"
    @click="emit('view')"
    @dragstart="handleDragStart"
    @dragend="handleDragEnd"
  >
    <v-card-title class="d-flex justify-space-between align-center">
      <div class="text-truncate ml-2">{{ prompt.prompt_id }}</div>
      <v-menu offset-y>
        <template #activator="{ props: activatorProps }">
          <v-btn
            icon="mdi-dots-vertical"
            variant="text"
            size="small"
            v-bind="activatorProps"
            @click.stop
          />
        </template>
        <v-list density="compact">
          <v-list-item @click.stop="emit('edit')">
            <template #prepend>
              <v-icon size="small">mdi-pencil</v-icon>
            </template>
            <v-list-item-title>{{ tm('buttons.edit') }}</v-list-item-title>
          </v-list-item>
          <v-list-item @click.stop="emit('move')">
            <template #prepend>
              <v-icon size="small">mdi-folder-move</v-icon>
            </template>
            <v-list-item-title>{{
              tm('prompt.contextMenu.moveTo')
            }}</v-list-item-title>
          </v-list-item>
          <v-list-item @click.stop="exportPrompt">
            <template #prepend>
              <v-icon size="small">mdi-download</v-icon>
            </template>
            <v-list-item-title>{{ tm('buttons.export') }}</v-list-item-title>
          </v-list-item>
          <v-divider class="my-1" />
          <v-list-item class="text-error" @click.stop="emit('delete')">
            <template #prepend>
              <v-icon size="small" color="error">mdi-delete</v-icon>
            </template>
            <v-list-item-title>{{ tm('buttons.delete') }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-card-title>

    <v-card-text>
      <div class="system-prompt-preview">
        {{ truncateText(prompt.system_prompt, 100) }}
      </div>

      <div class="mt-3 d-flex flex-wrap ga-1">
        <v-chip
          v-if="prompt.begin_dialogs && prompt.begin_dialogs.length > 0"
          size="small"
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-chat"
        >
          {{
            tm('labels.presetDialogs', {
              count: prompt.begin_dialogs.length / 2,
            })
          }}
        </v-chip>
        <v-chip
          v-if="prompt.tools === null"
          size="small"
          color="success"
          variant="tonal"
          prepend-icon="mdi-tools"
        >
          {{ tm('form.allToolsAvailable') }}
        </v-chip>
        <v-chip
          v-else-if="prompt.tools && prompt.tools.length > 0"
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-tools"
        >
          {{ prompt.tools.length }} {{ tm('prompt.toolsCount') }}
        </v-chip>
        <v-chip
          v-if="prompt.skills === null"
          size="small"
          color="success"
          variant="tonal"
          prepend-icon="mdi-lightning-bolt"
        >
          {{ tm('form.allSkillsAvailable') }}
        </v-chip>
        <v-chip
          v-else-if="prompt.skills && prompt.skills.length > 0"
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-lightning-bolt"
        >
          {{ prompt.skills.length }} {{ tm('prompt.skillsCount') }}
        </v-chip>
      </div>

      <div class="mt-3 text-caption text-medium-emphasis">
        {{ tm('labels.createdAt') }}: {{ formatDate(prompt.created_at) }}
      </div>
    </v-card-text>
  </v-card>

  <!-- Custom Drag Preview -->
  <div ref="dragPreview" class="drag-preview">
    <v-icon size="small" class="mr-2">mdi-account</v-icon>
    <span class="text-subtitle-2">{{ prompt.prompt_id }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';

interface Prompt {
  prompt_id: string;
  system_prompt: string;
  custom_error_message?: string | null;
  begin_dialogs?: string[] | null;
  tools?: string[] | null;
  skills?: string[] | null;
  created_at?: string;
  updated_at?: string;
  folder_id?: string | null;
}

const props = defineProps<{
  prompt: Prompt;
}>();

const emit = defineEmits<{
  view: [];
  edit: [];
  move: [];
  delete: [];
  export: [message: string, isError: boolean];
}>();

const { tm } = useModuleI18n('features/prompt');
const confirmDialog = useConfirmDialog();
const dragPreview = ref<HTMLElement | null>(null);
const isDragging = ref(false);

function handleDragStart(event: DragEvent) {
  isDragging.value = true;
  if (!event.dataTransfer) {
    return;
  }
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData(
    'application/json',
    JSON.stringify({
      type: 'prompt',
      prompt_id: props.prompt.prompt_id,
      prompt: props.prompt,
    }),
  );

  if (dragPreview.value) {
    event.dataTransfer.setDragImage(dragPreview.value, 15, 15);
  }
}

function handleDragEnd() {
  isDragging.value = false;
}

function truncateText(
  text: string | undefined | null,
  maxLength: number,
): string {
  if (!text) {
    return '';
  }
  return text.length > maxLength ? `${text.substring(0, maxLength)}...` : text;
}

function formatDate(dateString: string | undefined | null): string {
  if (!dateString) {
    return '';
  }
  return new Date(dateString).toLocaleString();
}

async function exportPrompt() {
  if (
    !(await askForConfirmationDialog(
      tm('messages.exportConfirm'),
      confirmDialog,
    ))
  ) {
    return;
  }

  try {
    const exportData = {
      prompt_id: props.prompt.prompt_id,
      system_prompt: props.prompt.system_prompt,
      begin_dialogs: props.prompt.begin_dialogs || [],
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(exportData, null, 2)], {
        type: 'application/json',
      }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `prompt_${props.prompt.prompt_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
    emit('export', tm('messages.exportSuccess'), false);
  } catch (error) {
    console.error('Failed to export prompt:', error);
    emit('export', tm('messages.exportError', { error: String(error) }), true);
  }
}
</script>

<style scoped>
.prompt-card {
  background: rgb(var(--v-theme-surface));
  height: 100%;
  cursor: grab;
  transition:
    background-color 0.16s ease,
    opacity 0.2s ease,
    transform 0.2s ease;
}

.prompt-card:hover,
.prompt-card:focus-within {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.prompt-card:active {
  cursor: grabbing;
}

.prompt-card.dragging {
  opacity: 0.5;
  transform: scale(0.95);
}

.system-prompt-preview {
  font-size: 14px;
  line-height: 1.4;
  color: rgba(var(--v-theme-on-surface), 0.7);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
}

.drag-preview {
  position: fixed;
  top: -1000px;
  left: -1000px;
  background: rgb(var(--v-theme-surface));
  padding: 12px 20px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  z-index: 9999;
  pointer-events: none;
}
</style>

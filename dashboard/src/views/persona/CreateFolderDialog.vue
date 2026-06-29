<template>
  <BaseCreateFolderDialog
    ref="baseDialog"
    v-model="showDialog"
    :parent-folder-id="parentFolderId"
    :labels="labels"
    @create="handleCreate"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import BaseCreateFolderDialog from '@/components/folder/BaseCreateFolderDialog.vue';
import type { CreateFolderData } from '@/components/folder/types';
import { resolveErrorMessage } from '@/utils/errorUtils';

type BaseCreateFolderDialogExposed = {
  setLoading: (value: boolean) => void;
};

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    parentFolderId?: string | null;
  }>(),
  {
    modelValue: false,
    parentFolderId: null,
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  created: [message: string];
  error: [message: string];
}>();

const { tm } = useModuleI18n('features/persona');
const personaStore = usePersonaStore();
const baseDialog = ref<BaseCreateFolderDialogExposed | null>(null);

const showDialog = computed({
  get: () => props.modelValue,
  set: (value: boolean) => void emit('update:modelValue', value),
});

const labels = computed(() => ({
  title: tm('folder.createDialog.title'),
  nameLabel: tm('folder.form.name'),
  descriptionLabel: tm('folder.form.description'),
  nameRequired: tm('folder.validation.nameRequired'),
  cancelButton: tm('buttons.cancel'),
  createButton: tm('folder.createDialog.createButton'),
}));

async function handleCreate(data: CreateFolderData) {
  baseDialog.value?.setLoading(true);
  try {
    await personaStore.createFolder({
      name: data.name,
      description: data.description,
      parent_id: data.parent_id,
    });
    emit('created', tm('folder.messages.createSuccess'));
    showDialog.value = false;
  } catch (error) {
    emit(
      'error',
      resolveErrorMessage(error, tm('folder.messages.createError')),
    );
  } finally {
    baseDialog.value?.setLoading(false);
  }
}
</script>

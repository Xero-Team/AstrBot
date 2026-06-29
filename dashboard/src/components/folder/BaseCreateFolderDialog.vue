<template>
  <v-dialog v-model="showDialog" max-width="450px">
    <v-card>
      <v-card-title>
        <v-icon class="mr-2">mdi-folder-plus</v-icon>
        {{ mergedLabels.title }}
      </v-card-title>
      <v-card-text>
        <v-form
          ref="form"
          v-model="formValid"
          :disabled="loading"
          @submit.prevent="submitForm"
        >
          <v-text-field
            v-model="formData.name"
            :label="mergedLabels.nameLabel"
            :rules="[
              (v: string | null | undefined) =>
                !!v || mergedLabels.nameRequired,
            ]"
            variant="outlined"
            density="comfortable"
            autofocus
            class="mb-3"
          />

          <v-textarea
            v-model="formData.description"
            :label="mergedLabels.descriptionLabel"
            variant="outlined"
            rows="3"
            density="comfortable"
            hide-details
          />
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="closeDialog">
          {{ mergedLabels.cancelButton }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="loading"
          :disabled="!formValid"
          @click="submitForm"
        >
          {{ mergedLabels.createButton }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import type { CreateFolderData } from './types';

interface FormController {
  resetValidation: () => void;
}

interface DefaultLabels {
  title: string;
  nameLabel: string;
  descriptionLabel: string;
  nameRequired: string;
  cancelButton: string;
  createButton: string;
}

const defaultLabels: DefaultLabels = {
  title: '创建文件夹',
  nameLabel: '名称',
  descriptionLabel: '描述',
  nameRequired: '请输入文件夹名称',
  cancelButton: '取消',
  createButton: '创建',
};

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    parentFolderId?: string | null;
    labels?: Partial<DefaultLabels>;
  }>(),
  {
    modelValue: false,
    parentFolderId: null,
    labels: () => ({}),
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  create: [data: CreateFolderData];
}>();

const form = ref<FormController | null>(null);
const formValid = ref(false);
const loading = ref(false);
const formData = reactive({
  name: '',
  description: '',
});

const showDialog = computed({
  get: () => props.modelValue,
  set: (value: boolean) => void emit('update:modelValue', value),
});

const mergedLabels = computed<DefaultLabels>(() => ({
  ...defaultLabels,
  ...props.labels,
}));

watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue) {
      resetForm();
    }
  },
);

function resetForm() {
  formData.name = '';
  formData.description = '';
  form.value?.resetValidation();
}

function closeDialog() {
  showDialog.value = false;
}

function submitForm() {
  if (!formValid.value) {
    return;
  }

  emit('create', {
    name: formData.name,
    description: formData.description || undefined,
    parent_id: props.parentFolderId,
  });
}

function setLoading(value: boolean) {
  loading.value = value;
}

defineExpose({
  resetForm,
  setLoading,
});
</script>

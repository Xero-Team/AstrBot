<template>
  <div class="skills-page">
    <v-container fluid class="pa-0">
      <SkillsLocalList
        :loading="loading"
        :total-skills="skills.length"
        :result-count="filteredSkills.length"
        :search="skillSearch"
        @update:search="skillSearch = $event"
      >
        <template #actions>
          <template v-if="batchSelectionEnabled">
            <v-btn
              variant="text"
              size="small"
              :disabled="batchDeleting"
              @click="toggleSelectAll"
            >
              {{
                allDeletableSelected
                  ? tm('skills.clearSelection')
                  : tm('skills.selectAll')
              }}
            </v-btn>
            <v-btn
              color="error"
              variant="tonal"
              size="small"
              prepend-icon="mdi-delete-outline"
              :disabled="selectedSkillNames.length === 0 || batchDeleting"
              @click="confirmBatchDelete"
            >
              {{
                tm('skills.deleteSelected', {
                  count: selectedSkillNames.length,
                })
              }}
            </v-btn>
            <v-btn
              variant="text"
              size="small"
              :disabled="batchDeleting"
              @click="cancelBatchSelection"
            >
              {{ tm('skills.cancel') }}
            </v-btn>
          </template>
          <v-btn
            v-else
            variant="tonal"
            size="small"
            prepend-icon="mdi-select-multiple"
            :disabled="visibleDeletableSkills.length === 0"
            @click="startBatchSelection"
          >
            {{ tm('skills.select') }}
          </v-btn>
        </template>

        <SkillListItem
          v-for="skill in filteredSkills"
          :key="skill.name"
          v-model:selected-names="selectedSkillNames"
          :name="skill.name"
          :description="skill.description"
          :path="skill.path"
          :active="skill.active"
          :source-color="sourceTypeColor(skill.source_type)"
          :source-label="sourceTypeLabel(skill.source_type, skill)"
          :read-only="isReadOnlySourceSkill(skill)"
          :inactive-plugin="isInactivePluginSkill(skill)"
          :loading="Boolean(itemLoading[skill.name])"
          :batch-selection-enabled="batchSelectionEnabled"
          :batch-deleting="batchDeleting"
          :clickable="!batchSelectionEnabled"
          :class="{
            'skill-list-item--inactive': isInactivePluginSkill(skill),
            'skill-list-item--selected':
              batchSelectionEnabled && selectedSkillNames.includes(skill.name),
          }"
          @open="openSkillEditor(skill)"
          @download="downloadSkill(skill)"
          @delete="confirmDelete(skill)"
          @toggle="toggleSkill(skill)"
        />
      </SkillsLocalList>
    </v-container>

    <SkillsFabStack @refresh="fetchSkills" @upload="openUploadDialog" />

    <SkillUploadDialog
      :show="uploadDialog"
      :uploading="uploading"
      :items="uploadItems"
      @update:show="uploadDialog = $event"
      @close="closeUploadDialog"
      @add-files="addUploadFiles"
      @remove="removeUploadItem"
      @confirm="uploadSkillBatch"
    />

    <SkillDeleteDialog
      :show="deleteDialog"
      :deleting="deleting"
      @update:show="deleteDialog = $event"
      @confirm="deleteSkill"
    />

    <SkillBatchDeleteDialog
      :show="batchDeleteDialog"
      :targets="batchDeleteTargets"
      :deleting="batchDeleting"
      @update:show="batchDeleteDialog = $event"
      @confirm="deleteSelectedSkills"
    />

    <SkillEditorDialog
      :show="editorDialog.show"
      :fullscreen="$vuetify.display.mdAndDown"
      :skill-name="editorDialog.skillName"
      :current-dir="editorDialog.currentDir"
      :entries="editorDialog.entries"
      :file-path="editorDialog.filePath"
      :content="editorDialog.content"
      :file-editable="editorDialog.fileEditable"
      :file-dirty="editorDialog.fileDirty"
      :loading-files="editorDialog.loadingFiles"
      :loading-file="editorDialog.loadingFile"
      :saving="editorDialog.saving"
      :error="editorDialog.error"
      @update:show="editorDialog.show = $event"
      @update:content="editorDialog.content = $event"
      @dirty="editorDialog.fileDirty = true"
      @open-entry="openSkillEntry"
      @open-parent="openParentSkillDir"
      @save="saveSkillFile"
      @close="closeSkillEditor"
    />

    <v-snackbar
      v-model="snackbar.show"
      :timeout="3500"
      :color="snackbar.color"
      elevation="4"
    >
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import type { SkillItemData } from '@/api/v1';
import { skillApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { buildSearchQuery, matchesText } from '@/utils/pluginSearch';
import SkillsLocalList from './SkillsLocalList.vue';
import SkillsFabStack from './skills/SkillsFabStack.vue';
import SkillListItem from './skills/SkillListItem.vue';
import SkillUploadDialog from './SkillUploadDialog.vue';
import SkillDeleteDialog from './SkillDeleteDialog.vue';
import SkillBatchDeleteDialog from './SkillBatchDeleteDialog.vue';
import SkillEditorDialog from './SkillEditorDialog.vue';
import {
  STATUS_ERROR,
  STATUS_SKIPPED,
  STATUS_SUCCESS,
  STATUS_UPLOADING,
  STATUS_WAITING,
  asRecord,
  getBoolean,
  getString,
  normalizeSkillEntry,
  normalizeUploadName,
  type EditorDialogState,
  type SkillEntry,
  type SnackbarColor,
  type UploadItem,
  type UploadResultEntry,
  type UploadStatus,
} from './skillsHelpers';

interface SkillItem extends SkillItemData {
  name: string;
  description: string;
  path: string;
  active: boolean;
  source_type?: string;
  source_label?: string;
  plugin_name?: string;
  plugin_active?: boolean;
  plugin_display_name?: string;
  readonly?: boolean;
}

const { tm } = useModuleI18n('features/extension');

const skills = ref<SkillItem[]>([]);
const skillSearch = ref('');
const loading = ref(false);
const uploading = ref(false);
const uploadDialog = ref(false);
const uploadItems = ref<UploadItem[]>([]);
const itemLoading = reactive<Record<string, boolean>>({});
const deleteDialog = ref(false);
const deleting = ref(false);
const skillToDelete = ref<SkillItem | null>(null);
const batchSelectionEnabled = ref(false);
const selectedSkillNames = ref<string[]>([]);
const batchDeleteTargets = ref<string[]>([]);
const batchDeleteDialog = ref(false);
const batchDeleting = ref(false);
const snackbar = reactive<{
  show: boolean;
  message: string;
  color: SnackbarColor;
}>({
  show: false,
  message: '',
  color: 'success',
});

const editorDialog = reactive<EditorDialogState>({
  show: false,
  skillName: '',
  currentDir: '',
  entries: [],
  filePath: '',
  content: '',
  fileEditable: false,
  fileDirty: false,
  loadingFiles: false,
  loadingFile: false,
  saving: false,
  error: '',
});

let nextUploadItemId = 0;

function normalizeSkillItem(value: unknown): SkillItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const name = getString(record.name).trim();
  if (!name) {
    return null;
  }

  return {
    ...record,
    name,
    description: getString(record.description),
    path: getString(record.path),
    active: getBoolean(record.active),
    source_type: getString(record.source_type) || undefined,
    source_label: getString(record.source_label) || undefined,
    plugin_name: getString(record.plugin_name) || undefined,
    plugin_active:
      typeof record.plugin_active === 'boolean'
        ? record.plugin_active
        : undefined,
    plugin_display_name: getString(record.plugin_display_name) || undefined,
    readonly: getBoolean(record.readonly),
  };
}

function showMessage(message: string, color: SnackbarColor = 'success') {
  snackbar.message = message;
  snackbar.color = color;
  snackbar.show = true;
}

function normalizeSkillsPayload(payload: unknown) {
  if (Array.isArray(payload)) {
    return payload
      .map((skill) => normalizeSkillItem(skill))
      .filter((skill): skill is SkillItem => skill !== null);
  }

  const record = asRecord(payload);
  if (!record) {
    return [];
  }

  const skillList = Array.isArray(record.skills) ? record.skills : [];
  return skillList
    .map((skill) => normalizeSkillItem(skill))
    .filter((skill): skill is SkillItem => skill !== null);
}

function sourceTypeLabel(sourceType?: string, skill: SkillItem | null = null) {
  if (sourceType === 'plugin') {
    return tm('skills.sourcePlugin', {
      plugin: skill?.source_label || skill?.plugin_name || '',
    });
  }
  if (sourceType === 'builtin_preset') {
    return tm('skills.sourceBuiltin', {
      source: skill?.source_label || '',
    });
  }
  return tm('skills.sourceLocalOnly');
}

function sourceTypeColor(sourceType?: string) {
  if (sourceType === 'plugin') return 'secondary';
  if (sourceType === 'builtin_preset') return 'teal';
  return 'primary';
}

function isPluginProvidedSkill(skill: SkillItem) {
  return skill.source_type === 'plugin';
}

function isInactivePluginSkill(skill: SkillItem) {
  return isPluginProvidedSkill(skill) && skill.plugin_active === false;
}

function isBuiltinPresetSkill(skill: SkillItem) {
  return skill.source_type === 'builtin_preset';
}

function isReadOnlySourceSkill(skill: SkillItem) {
  return (
    skill.readonly === true ||
    isPluginProvidedSkill(skill) ||
    isBuiltinPresetSkill(skill)
  );
}

const filteredSkills = computed(() => {
  const query = buildSearchQuery(skillSearch.value);
  if (!query) return skills.value;
  return skills.value.filter((skill) =>
    [skill.name, skill.description, skill.path].some((field) =>
      matchesText(field, query),
    ),
  );
});

// Select-all only applies to the currently visible (filtered) deletable skills.
const visibleDeletableSkills = computed(() =>
  filteredSkills.value.filter((skill) => !isReadOnlySourceSkill(skill)),
);

const allDeletableSelected = computed(
  () =>
    visibleDeletableSkills.value.length > 0 &&
    visibleDeletableSkills.value.every((skill) =>
      selectedSkillNames.value.includes(skill.name),
    ),
);

function showReadOnlySkillMessage(skill: SkillItem) {
  if (isPluginProvidedSkill(skill)) {
    showMessage(tm('skills.pluginReadonly'), 'warning');
    return;
  }
  if (isBuiltinPresetSkill(skill)) {
    showMessage(tm('skills.builtinReadonly'), 'warning');
  }
}

function buildUploadItem(
  file: File,
  status: UploadStatus,
  validationMessage: string,
): UploadItem {
  return {
    id: `upload-${nextUploadItemId++}`,
    file,
    name: file.name,
    size: file.size,
    status,
    validationMessage,
    filenameKey: normalizeUploadName(file.name),
  };
}

function resetUploadState() {
  uploadItems.value = [];
}

function openUploadDialog() {
  uploadDialog.value = true;
}

function closeUploadDialog() {
  if (uploading.value) return;
  uploadDialog.value = false;
}

function addUploadFiles(filesToAdd: File[]) {
  const existingNames = new Set(
    uploadItems.value.map((item) => item.filenameKey),
  );
  const nextItems: UploadItem[] = [];

  for (const file of filesToAdd) {
    if (!file.name) continue;
    const filenameKey = normalizeUploadName(file.name);

    if (existingNames.has(filenameKey)) {
      nextItems.push(
        buildUploadItem(file, STATUS_SKIPPED, tm('skills.validationDuplicate')),
      );
      continue;
    }

    existingNames.add(filenameKey);
    if (!/\.zip$/i.test(file.name)) {
      nextItems.push(
        buildUploadItem(file, STATUS_SKIPPED, tm('skills.validationZipOnly')),
      );
      continue;
    }

    nextItems.push(
      buildUploadItem(file, STATUS_WAITING, tm('skills.validationReady')),
    );
  }

  if (nextItems.length > 0) {
    uploadItems.value = [...uploadItems.value, ...nextItems];
  }
}

function removeUploadItem(itemId: string) {
  uploadItems.value = uploadItems.value.filter((item) => item.id !== itemId);
}

function takeFirstMatch(
  matchMap: Map<string, UploadResultEntry[]>,
  filenameKey: string,
) {
  const matches = matchMap.get(filenameKey) || [];
  const entry = matches.shift() || null;
  if (matches.length === 0) {
    matchMap.delete(filenameKey);
  }
  return entry;
}

function buildResultMap(items: unknown): Map<string, UploadResultEntry[]> {
  const resultMap = new Map<string, UploadResultEntry[]>();
  if (!Array.isArray(items)) {
    return resultMap;
  }

  for (const item of items) {
    const record = asRecord(item);
    if (!record) {
      continue;
    }
    const entry: UploadResultEntry = {
      filename: getString(record.filename) || undefined,
      name: getString(record.name) || undefined,
      error: getString(record.error) || undefined,
    };
    const filenameKey = normalizeUploadName(entry.filename || '');
    if (!filenameKey) continue;
    if (!resultMap.has(filenameKey)) {
      resultMap.set(filenameKey, []);
    }
    resultMap.get(filenameKey)?.push(entry);
  }

  return resultMap;
}

function applyUploadResults(attemptedItems: UploadItem[], payload: unknown) {
  const payloadRecord = asRecord(payload);
  const succeededMap = buildResultMap(payloadRecord?.succeeded);
  const failedMap = buildResultMap(payloadRecord?.failed);
  const skippedMap = buildResultMap(payloadRecord?.skipped);

  for (const item of attemptedItems) {
    const successEntry = takeFirstMatch(succeededMap, item.filenameKey);
    if (successEntry) {
      item.status = STATUS_SUCCESS;
      item.validationMessage = tm('skills.validationUploadedAs', {
        name: successEntry.name || item.name,
      });
      continue;
    }

    const skippedEntry = takeFirstMatch(skippedMap, item.filenameKey);
    if (skippedEntry) {
      item.status = STATUS_SKIPPED;
      item.validationMessage =
        skippedEntry.error || tm('skills.validationDuplicate');
      continue;
    }

    const failedEntry = takeFirstMatch(failedMap, item.filenameKey);
    if (failedEntry) {
      item.status = STATUS_ERROR;
      item.validationMessage =
        failedEntry.error || tm('skills.validationUploadFailed');
      continue;
    }

    item.status = STATUS_ERROR;
    item.validationMessage = tm('skills.validationNoResult');
  }
}

async function fetchSkills() {
  loading.value = true;
  try {
    const res = await skillApi.list();
    skills.value = normalizeSkillsPayload(res.data.data);
    const deletableNames = new Set(
      skills.value
        .filter((skill) => !isReadOnlySourceSkill(skill))
        .map((skill) => skill.name),
    );
    selectedSkillNames.value = selectedSkillNames.value.filter((name) =>
      deletableNames.has(name),
    );
    if (batchSelectionEnabled.value && deletableNames.size === 0) {
      batchSelectionEnabled.value = false;
    }
    return true;
  } catch {
    showMessage(tm('skills.loadFailed'), 'error');
    return false;
  } finally {
    loading.value = false;
  }
}

function handleApiResponse(
  res: { data?: { status?: string; message?: string | null } },
  successMessage: string,
  failureMessageDefault: string,
  onSuccess?: () => void | Promise<void>,
) {
  if (res.data?.status === 'ok') {
    showMessage(successMessage, 'success');
    void onSuccess?.();
  } else {
    showMessage(res.data?.message || failureMessageDefault, 'error');
  }
}

async function uploadSkillBatch() {
  const attemptedItems = uploadItems.value.filter(
    (item) => item.status === STATUS_WAITING || item.status === STATUS_ERROR,
  );
  if (attemptedItems.length === 0) return;

  uploading.value = true;
  for (const item of attemptedItems) {
    item.status = STATUS_UPLOADING;
    item.validationMessage = tm('skills.validationUploading');
  }

  try {
    const res = await skillApi.uploadBatch(
      attemptedItems.map((item) => item.file),
    );
    applyUploadResults(attemptedItems, res.data.data);

    const payload = asRecord(res.data.data);
    const succeededCount = Array.isArray(payload?.succeeded)
      ? payload.succeeded.length
      : 0;
    const failedCount = Array.isArray(payload?.failed)
      ? payload.failed.length
      : 0;

    let responseColor: SnackbarColor = 'success';
    if (res.data.status === 'error') {
      responseColor = 'error';
    } else if (failedCount > 0) {
      responseColor = 'warning';
    }

    showMessage(res.data.message || tm('skills.uploadSuccess'), responseColor);

    if (succeededCount > 0) {
      await fetchSkills();
    }
  } catch {
    for (const item of attemptedItems) {
      item.status = STATUS_ERROR;
      item.validationMessage = tm('skills.validationUploadFailed');
    }
    showMessage(tm('skills.uploadFailed'), 'error');
  } finally {
    uploading.value = false;
  }
}

async function toggleSkill(skill: SkillItem) {
  if (isInactivePluginSkill(skill)) {
    showMessage(tm('skills.pluginDisabled'), 'warning');
    return;
  }
  if (isReadOnlySourceSkill(skill)) {
    showReadOnlySkillMessage(skill);
    return;
  }
  const nextActive = !skill.active;
  itemLoading[skill.name] = true;
  try {
    const res = await skillApi.setEnabled(skill.name, nextActive);
    handleApiResponse(
      res,
      tm('skills.updateSuccess'),
      tm('skills.updateFailed'),
      () => {
        skill.active = nextActive;
      },
    );
  } catch {
    showMessage(tm('skills.updateFailed'), 'error');
  } finally {
    itemLoading[skill.name] = false;
  }
}

function confirmDelete(skill: SkillItem) {
  if (isReadOnlySourceSkill(skill)) {
    showReadOnlySkillMessage(skill);
    return;
  }
  skillToDelete.value = skill;
  deleteDialog.value = true;
}

async function deleteSkill() {
  if (!skillToDelete.value) return;
  deleting.value = true;
  try {
    const res = await skillApi.delete(skillToDelete.value.name);
    handleApiResponse(
      res,
      tm('skills.deleteSuccess'),
      tm('skills.deleteFailed'),
      async () => {
        deleteDialog.value = false;
        await fetchSkills();
      },
    );
  } catch {
    showMessage(tm('skills.deleteFailed'), 'error');
  } finally {
    deleting.value = false;
  }
}

function startBatchSelection() {
  selectedSkillNames.value = [];
  batchDeleteTargets.value = [];
  batchSelectionEnabled.value = true;
}

function cancelBatchSelection() {
  if (batchDeleting.value) return;
  batchSelectionEnabled.value = false;
  selectedSkillNames.value = [];
  batchDeleteTargets.value = [];
  batchDeleteDialog.value = false;
}

function toggleSelectAll() {
  if (allDeletableSelected.value) {
    selectedSkillNames.value = [];
    return;
  }
  selectedSkillNames.value = visibleDeletableSkills.value.map(
    (skill) => skill.name,
  );
}

function confirmBatchDelete() {
  const selectedNames = new Set(selectedSkillNames.value);
  batchDeleteTargets.value = [
    ...new Set(
      visibleDeletableSkills.value
        .filter((skill) => selectedNames.has(skill.name))
        .map((skill) => skill.name),
    ),
  ];
  if (batchDeleteTargets.value.length === 0) return;
  batchDeleteDialog.value = true;
}

async function deleteSelectedSkills() {
  if (batchDeleting.value || batchDeleteTargets.value.length === 0) return;

  const targets = [...batchDeleteTargets.value];
  const failed: string[] = [];
  let succeeded = 0;
  batchDeleting.value = true;

  try {
    for (const name of targets) {
      try {
        const res = await skillApi.delete(name);
        if (res.data.status === 'ok') {
          succeeded += 1;
        } else {
          failed.push(name);
        }
      } catch {
        failed.push(name);
      }
    }

    const refreshed = await fetchSkills();
    if (refreshed) {
      const currentDeletableNames = new Set(
        skills.value
          .filter((skill) => !isReadOnlySourceSkill(skill))
          .map((skill) => skill.name),
      );
      selectedSkillNames.value = failed.filter((name) =>
        currentDeletableNames.has(name),
      );
    } else {
      selectedSkillNames.value = failed;
      batchSelectionEnabled.value = failed.length > 0;
    }
    batchDeleteDialog.value = false;
    batchDeleteTargets.value = [];

    if (!refreshed) return;

    if (failed.length === 0) {
      batchSelectionEnabled.value = false;
      showMessage(
        tm('skills.batchDeleteSuccess', { count: succeeded }),
        'success',
      );
    } else {
      showMessage(
        tm('skills.batchDeletePartial', {
          succeeded,
          failed: failed.length,
        }),
        'warning',
      );
    }
  } finally {
    batchDeleting.value = false;
  }
}

async function downloadSkill(skill: SkillItem) {
  if (isReadOnlySourceSkill(skill)) {
    showReadOnlySkillMessage(skill);
    return;
  }
  itemLoading[skill.name] = true;
  try {
    const res = await skillApi.download(skill.name);
    if (!(res.data instanceof Blob)) {
      throw new Error('Skill download did not return a blob payload');
    }
    const blob = res.data;
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${skill.name}.zip`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    showMessage(tm('skills.downloadSuccess'), 'success');
  } catch {
    showMessage(tm('skills.downloadFailed'), 'error');
  } finally {
    itemLoading[skill.name] = false;
  }
}

function resetEditorDialog() {
  editorDialog.skillName = '';
  editorDialog.currentDir = '';
  editorDialog.entries = [];
  editorDialog.filePath = '';
  editorDialog.content = '';
  editorDialog.fileEditable = false;
  editorDialog.fileDirty = false;
  editorDialog.loadingFiles = false;
  editorDialog.loadingFile = false;
  editorDialog.saving = false;
  editorDialog.error = '';
}

async function loadSkillDir(path = '') {
  if (!editorDialog.skillName) return [];
  editorDialog.loadingFiles = true;
  editorDialog.error = '';
  try {
    const res = await skillApi.listFiles(editorDialog.skillName, path);
    if (res.data.status !== 'ok') {
      editorDialog.error = res.data.message || tm('skills.editorLoadFailed');
      return [];
    }
    const payload = asRecord(res.data.data);
    editorDialog.currentDir = getString(payload?.path);
    editorDialog.entries = Array.isArray(payload?.entries)
      ? payload.entries
          .map((entry) => normalizeSkillEntry(entry))
          .filter((entry): entry is SkillEntry => entry !== null)
      : [];
    return editorDialog.entries;
  } catch {
    editorDialog.error = tm('skills.editorLoadFailed');
    return [];
  } finally {
    editorDialog.loadingFiles = false;
  }
}

async function loadSkillFile(path: string) {
  if (!editorDialog.skillName || !path) return;
  if (editorDialog.fileDirty && !window.confirm(tm('skills.discardChanges'))) {
    return;
  }
  editorDialog.loadingFile = true;
  editorDialog.error = '';
  try {
    const res = await skillApi.getFile(editorDialog.skillName, path);
    if (res.data.status !== 'ok') {
      editorDialog.error = res.data.message || tm('skills.editorLoadFailed');
      return;
    }
    const payload = asRecord(res.data.data);
    editorDialog.filePath = getString(payload?.path) || path;
    editorDialog.content = getString(payload?.content);
    editorDialog.fileEditable = payload?.editable !== false;
    await nextTick();
    editorDialog.fileDirty = false;
  } catch {
    editorDialog.error = tm('skills.editorLoadFailed');
  } finally {
    editorDialog.loadingFile = false;
  }
}

async function openSkillEditor(skill: SkillItem) {
  if (batchSelectionEnabled.value) return;
  resetEditorDialog();
  editorDialog.skillName = skill.name;
  editorDialog.show = true;
  const entries = await loadSkillDir('');
  const skillMd = entries.find((entry) => entry.path === 'SKILL.md');
  if (skillMd?.editable) {
    await loadSkillFile(skillMd.path);
  }
}

function closeSkillEditor() {
  if (editorDialog.saving) return;
  if (editorDialog.fileDirty && !window.confirm(tm('skills.discardChanges'))) {
    return;
  }
  editorDialog.show = false;
  resetEditorDialog();
}

async function openSkillEntry(entry: SkillEntry) {
  if (entry.type === 'directory') {
    if (
      editorDialog.fileDirty &&
      !window.confirm(tm('skills.discardChanges'))
    ) {
      return;
    }
    await loadSkillDir(entry.path);
    return;
  }
  await loadSkillFile(entry.path);
}

async function openParentSkillDir() {
  if (!editorDialog.currentDir) return;
  if (editorDialog.fileDirty && !window.confirm(tm('skills.discardChanges'))) {
    return;
  }
  const parts = editorDialog.currentDir.split('/').filter(Boolean);
  parts.pop();
  await loadSkillDir(parts.join('/'));
}

async function saveSkillFile() {
  if (
    !editorDialog.skillName ||
    !editorDialog.filePath ||
    !editorDialog.fileEditable
  ) {
    return;
  }
  editorDialog.saving = true;
  editorDialog.error = '';
  try {
    const res = await skillApi.updateFile(
      editorDialog.skillName,
      editorDialog.filePath,
      editorDialog.content,
    );
    if (res.data.status !== 'ok') {
      editorDialog.error = res.data.message || tm('skills.editorSaveFailed');
      showMessage(editorDialog.error, 'error');
      return;
    }
    editorDialog.fileDirty = false;
    showMessage(tm('skills.editorSaveSuccess'), 'success');
    await fetchSkills();
  } catch {
    editorDialog.error = tm('skills.editorSaveFailed');
    showMessage(tm('skills.editorSaveFailed'), 'error');
  } finally {
    editorDialog.saving = false;
  }
}

// Keep the batch selection in sync with the active filter so skills hidden
// by the search can never be included in a batch delete.
watch(visibleDeletableSkills, (visibleSkills) => {
  if (!batchSelectionEnabled.value) return;
  const visibleNames = new Set(visibleSkills.map((skill) => skill.name));
  selectedSkillNames.value = selectedSkillNames.value.filter((name) =>
    visibleNames.has(name),
  );
});

watch(uploadDialog, (isOpen) => {
  if (!isOpen && !uploading.value) {
    resetUploadState();
  }
});

onMounted(async () => {
  await fetchSkills();
});
</script>

<style scoped>
.skill-list-item--inactive {
  opacity: 0.58;
}

.skill-list-item--selected {
  background: rgba(var(--v-theme-primary), 0.06);
  border-color: rgba(var(--v-theme-primary), 0.5);
}

@media (max-width: 860px) {
  .skills-page :deep(.skill-editor-dialog) {
    height: auto;
    max-height: none;
    overflow-y: auto;
  }

  .skills-page :deep(.skill-editor) {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    min-height: 0;
  }

  .skills-page :deep(.skill-editor__files) {
    max-height: 20vh;
  }

  .skills-page :deep(.skill-editor__monaco) {
    min-height: 40vh;
  }
}
</style>

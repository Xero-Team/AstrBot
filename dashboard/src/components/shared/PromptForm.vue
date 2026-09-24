<template>
  <v-dialog
    v-model="showDialog"
    :max-width="smAndDown ? undefined : '1200px'"
    scrollable
    persistent
  >
    <v-card
      class="prompt-form-card"
      :class="{ 'prompt-form-card-mobile': smAndDown }"
    >
      <v-card-title class="prompt-form-title text-h2 px-6 pt-6 pl-6">
        {{
          editingPrompt ? tm('dialog.edit.title') : tm('dialog.create.title')
        }}
      </v-card-title>

      <v-card-text class="prompt-form-content">
        <!-- 创建位置提示 -->
        <v-alert
          v-if="!editingPrompt"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-folder-outline"
        >
          {{ tm('form.createInFolder', { folder: folderDisplayName }) }}
        </v-alert>

        <v-form v-model="formValid">
          <v-row class="prompt-form-layout">
            <v-col cols="12" md="6" class="prompt-basic-col">
              <v-text-field
                v-model="promptForm.prompt_id"
                :label="tm('form.promptId')"
                :rules="promptIdRules"
                :disabled="Boolean(editingPrompt)"
                variant="outlined"
                density="comfortable"
                class="mb-4"
              />

              <v-textarea
                v-model="promptForm.system_prompt"
                :label="tm('form.systemPrompt')"
                :rules="systemPromptRules"
                variant="outlined"
                rows="16"
                class="mb-4"
              />

              <v-textarea
                v-model="promptForm.custom_error_message"
                :label="tm('form.customErrorMessage')"
                :hint="tm('form.customErrorMessageHelp')"
                variant="outlined"
                rows="4"
                persistent-hint
                clearable
                class="mb-4"
              />
            </v-col>

            <v-col cols="12" md="6" class="prompt-panels-col">
              <v-expansion-panels v-model="expandedPanels" multiple>
                <!-- 工具选择面板 -->
                <v-expansion-panel value="tools">
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-tools</v-icon>
                    {{ tm('form.tools') }}
                    <v-chip
                      v-if="
                        Array.isArray(promptForm.tools) &&
                        promptForm.tools.length > 0
                      "
                      size="small"
                      color="primary"
                      variant="tonal"
                      class="ml-2"
                    >
                      {{ promptForm.tools.length }}
                    </v-chip>
                  </v-expansion-panel-title>

                  <v-expansion-panel-text>
                    <div class="mb-3">
                      <p class="text-body-2 text-medium-emphasis">
                        {{ tm('form.toolsHelp') }}
                      </p>
                    </div>

                    <v-radio-group
                      v-model="toolSelectValue"
                      class="mt-2"
                      :hide-details="true"
                    >
                      <v-radio label="默认使用全部函数工具" value="0"></v-radio>
                      <v-radio label="选择指定函数工具" value="1"> </v-radio>
                    </v-radio-group>

                    <div
                      v-if="toolSelectValue === '1'"
                      class="mt-3 selected-config-area"
                    >
                      <!-- 工具搜索 -->
                      <v-text-field
                        v-model="toolSearch"
                        :label="tm('form.searchTools')"
                        prepend-inner-icon="mdi-magnify"
                        variant="outlined"
                        density="compact"
                        hide-details
                        clearable
                        class="mb-3"
                      />

                      <!-- MCP 服务器 -->
                      <div v-if="mcpServers.length > 0" class="mb-4">
                        <h4 class="text-subtitle-2 mb-2">
                          {{ tm('form.mcpServersQuickSelect') }}
                        </h4>
                        <div class="d-flex flex-wrap ga-2">
                          <v-chip
                            v-for="server in mcpServers"
                            :key="server.name"
                            :color="
                              isServerSelected(server) ? 'primary' : 'default'
                            "
                            :variant="
                              isServerSelected(server) ? 'flat' : 'outlined'
                            "
                            size="small"
                            clickable
                            :disabled="
                              !server.tools || server.tools.length === 0
                            "
                            @click="toggleMcpServer(server)"
                          >
                            <v-icon start size="small">mdi-server</v-icon>
                            {{ server.name }}
                            <span v-if="server.tools" class="ml-1">
                              ({{ server.tools.length }})
                            </span>
                          </v-chip>
                        </div>
                      </div>

                      <!-- 工具选择列表 -->
                      <div
                        v-if="filteredTools.length > 0"
                        class="tools-selection"
                      >
                        <v-virtual-scroll
                          :items="filteredTools"
                          height="300"
                          item-height="72"
                        >
                          <template #default="{ item }">
                            <v-tooltip
                              :disabled="!isBuiltinTool(item)"
                              location="top"
                            >
                              <template #activator="{ props: tooltipProps }">
                                <div v-bind="tooltipProps">
                                  <v-list-item
                                    :key="item.name"
                                    density="comfortable"
                                    :disabled="isBuiltinTool(item)"
                                    @click="toggleTool(item.name)"
                                  >
                                    <template #prepend>
                                      <v-checkbox-btn
                                        v-if="!isBuiltinTool(item)"
                                        :model-value="isToolSelected(item.name)"
                                        @click.stop="toggleTool(item.name)"
                                      />
                                      <div
                                        v-else
                                        class="builtin-tool-checkbox-placeholder"
                                      />
                                    </template>

                                    <v-list-item-title>
                                      {{ item.name }}

                                      <v-chip
                                        v-if="item.origin"
                                        size="x-small"
                                        color="info"
                                        class="mr-2"
                                        variant="tonal"
                                      >
                                        {{ item.origin }}
                                      </v-chip>
                                      <v-chip
                                        v-if="item.origin_name"
                                        size="x-small"
                                        color="info"
                                        variant="outlined"
                                      >
                                        {{ item.origin_name }}
                                      </v-chip>
                                    </v-list-item-title>

                                    <v-list-item-subtitle
                                      v-if="item.description"
                                    >
                                      {{ truncateText(item.description, 100) }}
                                    </v-list-item-subtitle>
                                  </v-list-item>
                                </div>
                              </template>
                              <span>{{
                                tm('form.builtinToolDisabledHint')
                              }}</span>
                            </v-tooltip>
                          </template>
                        </v-virtual-scroll>
                      </div>

                      <div
                        v-else-if="!loadingTools && availableTools.length === 0"
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-tools</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noToolsAvailable') }}
                        </p>
                      </div>

                      <div
                        v-else-if="!loadingTools && filteredTools.length === 0"
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-magnify</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noToolsFound') }}
                        </p>
                      </div>

                      <!-- 加载状态 -->
                      <div v-if="loadingTools" class="text-center pa-4">
                        <v-progress-circular indeterminate color="primary" />
                        <p class="text-body-2 text-medium-emphasis mt-2">
                          {{ tm('form.loadingTools') }}
                        </p>
                      </div>

                      <!-- 已选择的工具 -->
                      <div class="mt-4">
                        <h4 class="text-subtitle-2 mb-2">
                          {{ tm('form.selectedTools') }}
                          <span
                            v-if="promptForm.tools === null"
                            class="text-success"
                          >
                            ({{ tm('form.allSelected') }})
                          </span>
                          <span v-else-if="Array.isArray(promptForm.tools)">
                            ({{ promptForm.tools.length }})
                          </span>
                        </h4>
                        <div
                          v-if="
                            Array.isArray(promptForm.tools) &&
                            promptForm.tools.length > 0
                          "
                          class="prompt-form__selected-list d-flex flex-wrap ga-1"
                        >
                          <v-tooltip
                            v-for="toolName in promptForm.tools"
                            :key="toolName"
                            :disabled="!isBuiltinToolName(toolName)"
                            location="top"
                          >
                            <template #activator="{ props: tooltipProps }">
                              <v-chip
                                v-bind="tooltipProps"
                                size="small"
                                color="primary"
                                variant="tonal"
                                :closable="!isBuiltinToolName(toolName)"
                                @click:close="removeTool(toolName)"
                              >
                                {{ toolName }}
                              </v-chip>
                            </template>
                            <span>{{
                              tm('form.builtinToolDisabledHint')
                            }}</span>
                          </v-tooltip>
                        </div>
                        <div v-else class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noToolsSelected') }}
                        </div>
                      </div>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- Skills 选择面板 -->
                <v-expansion-panel value="skills">
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-lightning-bolt</v-icon>
                    {{ tm('form.skills') }}
                    <v-chip
                      v-if="
                        Array.isArray(promptForm.skills) &&
                        promptForm.skills.length > 0
                      "
                      size="small"
                      color="primary"
                      variant="tonal"
                      class="ml-2"
                    >
                      {{ promptForm.skills.length }}
                    </v-chip>
                  </v-expansion-panel-title>

                  <v-expansion-panel-text>
                    <div class="mb-3">
                      <p class="text-body-2 text-medium-emphasis">
                        {{ tm('form.skillsHelp') }}
                      </p>
                    </div>

                    <v-radio-group
                      v-model="skillSelectValue"
                      class="mt-2"
                      :hide-details="true"
                    >
                      <v-radio
                        :label="tm('form.skillsAllAvailable')"
                        value="0"
                      ></v-radio>
                      <v-radio
                        :label="tm('form.skillsSelectSpecific')"
                        value="1"
                      ></v-radio>
                    </v-radio-group>

                    <div
                      v-if="skillSelectValue === '1'"
                      class="mt-3 selected-config-area"
                    >
                      <v-text-field
                        v-model="skillSearch"
                        :label="tm('form.searchSkills')"
                        prepend-inner-icon="mdi-magnify"
                        variant="outlined"
                        density="compact"
                        hide-details
                        clearable
                        class="mb-3"
                      />

                      <div
                        v-if="filteredSkills.length > 0"
                        class="skills-selection"
                      >
                        <v-virtual-scroll
                          :items="filteredSkills"
                          height="240"
                          item-height="48"
                        >
                          <template #default="{ item }">
                            <v-list-item
                              :key="item.name"
                              density="comfortable"
                              @click="toggleSkill(item.name)"
                            >
                              <template #prepend>
                                <v-checkbox-btn
                                  :model-value="isSkillSelected(item.name)"
                                  @click.stop="toggleSkill(item.name)"
                                />
                              </template>
                              <v-list-item-title>
                                {{ item.name }}
                              </v-list-item-title>
                              <v-list-item-subtitle v-if="item.description">
                                {{ truncateText(item.description, 100) }}
                              </v-list-item-subtitle>
                            </v-list-item>
                          </template>
                        </v-virtual-scroll>
                      </div>

                      <div
                        v-else-if="
                          !loadingSkills && availableSkills.length === 0
                        "
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-lightning-bolt</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noSkillsAvailable') }}
                        </p>
                      </div>

                      <div
                        v-else-if="
                          !loadingSkills && filteredSkills.length === 0
                        "
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-magnify</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noSkillsFound') }}
                        </p>
                      </div>

                      <div v-if="loadingSkills" class="text-center pa-4">
                        <v-progress-circular indeterminate color="primary" />
                        <p class="text-body-2 text-medium-emphasis mt-2">
                          {{ tm('form.loadingSkills') }}
                        </p>
                      </div>

                      <div class="mt-4">
                        <h4 class="text-subtitle-2 mb-2">
                          {{ tm('form.selectedSkills') }}
                          <span
                            v-if="promptForm.skills === null"
                            class="text-success"
                          >
                            ({{ tm('form.allSelected') }})
                          </span>
                          <span v-else-if="Array.isArray(promptForm.skills)">
                            ({{ promptForm.skills.length }})
                          </span>
                        </h4>
                        <div
                          v-if="
                            Array.isArray(promptForm.skills) &&
                            promptForm.skills.length > 0
                          "
                          class="prompt-form__selected-list d-flex flex-wrap ga-1"
                        >
                          <v-chip
                            v-for="skillName in promptForm.skills"
                            :key="skillName"
                            size="small"
                            color="primary"
                            variant="tonal"
                            closable
                            @click:close="removeSkill(skillName)"
                          >
                            {{ skillName }}
                          </v-chip>
                        </div>
                        <div v-else class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noSkillsSelected') }}
                        </div>
                      </div>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- 预设对话面板 -->
                <v-expansion-panel value="dialogs">
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-chat</v-icon>
                    {{ tm('form.presetDialogs') }}
                    <v-chip
                      v-if="promptForm.begin_dialogs.length > 0"
                      size="small"
                      color="primary"
                      variant="tonal"
                      class="ml-2"
                    >
                      {{ promptForm.begin_dialogs.length / 2 }}
                    </v-chip>
                  </v-expansion-panel-title>

                  <v-expansion-panel-text>
                    <div class="mb-3">
                      <p class="text-body-2 text-medium-emphasis">
                        {{ tm('form.presetDialogsHelp') }}
                      </p>
                    </div>

                    <div
                      v-for="(dialog, index) in promptForm.begin_dialogs"
                      :key="index"
                      class="mb-3"
                    >
                      <v-textarea
                        v-model="promptForm.begin_dialogs[index]"
                        :label="
                          index % 2 === 0
                            ? tm('form.userMessage')
                            : tm('form.assistantMessage')
                        "
                        :rules="getDialogRules(index)"
                        variant="outlined"
                        rows="2"
                        density="comfortable"
                      >
                        <template #append>
                          <v-btn
                            icon="mdi-delete"
                            variant="text"
                            size="small"
                            color="error"
                            @click="removeDialog(index)"
                          />
                        </template>
                      </v-textarea>
                    </div>

                    <v-btn
                      variant="outlined"
                      prepend-icon="mdi-plus"
                      block
                      @click="addDialogPair"
                    >
                      {{ tm('buttons.addDialogPair') }}
                    </v-btn>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>

      <v-card-actions class="prompt-form-actions">
        <v-btn
          v-if="editingPrompt"
          color="error"
          variant="text"
          @click="deletePrompt"
        >
          {{ tm('buttons.delete') }}
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="closeDialog">
          {{ tm('buttons.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          :disabled="!formValid"
          @click="savePrompt"
        >
          {{ tm('buttons.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import {
  mcpApi,
  promptApi,
  skillApi,
  toolApi,
  type PromptData,
  type PromptInput,
} from '@/api/v1';
import type { ToolItem } from '@/domain/tools';
import { useModuleI18n } from '@/i18n/composables';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import { useDisplay } from 'vuetify';

type SelectionMode = '0' | '1';
type PanelKey = 'tools' | 'skills' | 'dialogs';
type RuleResult = true | string;
type PromptRule = (value: string) => RuleResult;

interface EditablePrompt {
  prompt_id: PromptData['prompt_id'];
  system_prompt: PromptData['system_prompt'];
  custom_error_message?: PromptData['custom_error_message'];
  begin_dialogs?: string[] | null;
  tools?: string[] | null;
  skills?: string[] | null;
  folder_id?: string | null;
}

interface PromptFormState {
  prompt_id: string;
  system_prompt: string;
  custom_error_message: string;
  begin_dialogs: string[];
  tools: string[] | null;
  skills: string[] | null;
  folder_id: string | null;
}

interface McpServerItem {
  name: string;
  tools: string[];
}

interface PromptToolItem extends Pick<
  ToolItem,
  'name' | 'description' | 'origin' | 'origin_name' | 'readonly'
> {
  mcp_server_name?: string;
}

interface SkillItemOption {
  name: string;
  description: string;
  active: boolean;
  source_type?: string;
  plugin_active?: boolean;
  plugin_display_name?: string;
}

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    editingPrompt?: EditablePrompt | null;
    currentFolderId?: string | null;
    currentFolderName?: string | null;
  }>(),
  {
    modelValue: false,
    editingPrompt: null,
    currentFolderId: null,
    currentFolderName: null,
  },
);

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void;
  (event: 'saved', message: string): void;
  (event: 'error', message: string): void;
  (event: 'deleted', message: string): void;
}>();

const { tm } = useModuleI18n('features/prompt');
const confirmDialog = useConfirmDialog();
const { smAndDown } = useDisplay();

const toolSelectValue = ref<SelectionMode>('0');
const skillSelectValue = ref<SelectionMode>('0');
const saving = ref(false);
const expandedPanels = ref<PanelKey[]>([]);
const formValid = ref(false);
const mcpServers = ref<McpServerItem[]>([]);
const availableTools = ref<PromptToolItem[]>([]);
const loadingTools = ref(false);
const availableSkills = ref<SkillItemOption[]>([]);
const loadingSkills = ref(false);
const existingPromptIds = ref<string[]>([]);
const toolSearch = ref('');
const skillSearch = ref('');
const promptForm = reactive<PromptFormState>(
  createEmptyPromptForm(props.currentFolderId),
);

const showDialog = computed({
  get: () => props.modelValue,
  set: (value: boolean) => void emit('update:modelValue', value),
});

const promptIdRules = computed<PromptRule[]>(() => [
  (value) => Boolean(value) || tm('validation.required'),
  (value) =>
    (value.length >= 1 && true) || tm('validation.minLength', { min: 1 }),
  (value) =>
    props.editingPrompt?.prompt_id === value ||
    !existingPromptIds.value.includes(value) ||
    tm('validation.promptIdExists'),
]);

const systemPromptRules = computed<PromptRule[]>(() => [
  (value) => Boolean(value) || tm('validation.required'),
  (value) =>
    (value.trim().length >= 10 && true) ||
    tm('validation.minLength', { min: 10 }),
]);

const filteredTools = computed(() => {
  const search = toolSearch.value.trim().toLowerCase();
  if (!search) {
    return availableTools.value;
  }
  return availableTools.value.filter(
    (tool) =>
      tool.name.toLowerCase().includes(search) ||
      tool.description.toLowerCase().includes(search) ||
      tool.mcp_server_name?.toLowerCase().includes(search),
  );
});

const filteredSkills = computed(() => {
  const search = skillSearch.value.trim().toLowerCase();
  if (!search) {
    return availableSkills.value;
  }
  return availableSkills.value.filter(
    (skill) =>
      skill.name.toLowerCase().includes(search) ||
      skill.description.toLowerCase().includes(search),
  );
});

const folderDisplayName = computed(() => {
  if (props.currentFolderName) {
    return props.currentFolderName;
  }
  if (!props.currentFolderId) {
    return tm('form.rootFolder');
  }
  return props.currentFolderId;
});

watch(
  () => props.modelValue,
  (newValue) => {
    if (!newValue) {
      return;
    }
    if (props.editingPrompt) {
      initFormWithPrompt(props.editingPrompt);
    } else {
      initForm();
      void loadExistingPromptIds();
    }
    void loadMcpServers();
    void loadTools();
    void loadSkills();
  },
);

watch(
  () => props.editingPrompt,
  (newPrompt) => {
    if (!props.modelValue) {
      return;
    }
    if (newPrompt) {
      initFormWithPrompt(newPrompt);
      return;
    }
    initForm();
  },
  { immediate: true },
);

watch(toolSelectValue, (newValue) => {
  if (newValue === '0') {
    promptForm.tools = null;
  } else if (promptForm.tools === null) {
    promptForm.tools = [];
  }
});

watch(skillSelectValue, (newValue) => {
  if (newValue === '0') {
    promptForm.skills = null;
  } else if (promptForm.skills === null) {
    promptForm.skills = [];
  }
});

function createEmptyPromptForm(
  folderId: string | null | undefined,
): PromptFormState {
  return {
    prompt_id: '',
    system_prompt: '',
    custom_error_message: '',
    begin_dialogs: [],
    tools: [],
    skills: [],
    folder_id: folderId ?? null,
  };
}

function cloneStringList(value: string[] | null | undefined): string[] | null {
  if (value === null) {
    return null;
  }
  return Array.isArray(value) ? [...value] : [];
}

function applyPromptForm(next: PromptFormState) {
  promptForm.prompt_id = next.prompt_id;
  promptForm.system_prompt = next.system_prompt;
  promptForm.custom_error_message = next.custom_error_message;
  promptForm.begin_dialogs = [...next.begin_dialogs];
  promptForm.tools = cloneStringList(next.tools);
  promptForm.skills = cloneStringList(next.skills);
  promptForm.folder_id = next.folder_id;
}

function initForm() {
  applyPromptForm(createEmptyPromptForm(props.currentFolderId));
  toolSelectValue.value = '0';
  skillSelectValue.value = '0';
  expandedPanels.value = getDefaultExpandedPanels();
}

function initFormWithPrompt(prompt: EditablePrompt) {
  applyPromptForm({
    prompt_id: prompt.prompt_id,
    system_prompt: prompt.system_prompt,
    custom_error_message: prompt.custom_error_message ?? '',
    begin_dialogs: Array.isArray(prompt.begin_dialogs)
      ? [...prompt.begin_dialogs]
      : [],
    tools: cloneStringList(prompt.tools),
    skills: cloneStringList(prompt.skills),
    folder_id: prompt.folder_id ?? null,
  });
  toolSelectValue.value = prompt.tools === null ? '0' : '1';
  skillSelectValue.value = prompt.skills === null ? '0' : '1';
  expandedPanels.value = getDefaultExpandedPanels();
}

function getDefaultExpandedPanels(): PanelKey[] {
  return smAndDown.value ? [] : ['tools', 'skills', 'dialogs'];
}

function closeDialog() {
  showDialog.value = false;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function getString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function getBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function getStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    const record = asRecord(error);
    const response = asRecord(record?.response);
    const data = asRecord(response?.data);
    return getString(data?.message) ?? error.message;
  }
  const record = asRecord(error);
  const response = asRecord(record?.response);
  const data = asRecord(response?.data);
  return getString(data?.message) ?? fallback;
}

function normalizeMcpServer(value: unknown): McpServerItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const name = getString(record?.name);
  if (!name) {
    return null;
  }
  return {
    name,
    tools: getStringArray(record.tools),
  };
}

function normalizeToolItem(value: unknown): PromptToolItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const name = getString(record?.name);
  if (!name) {
    return null;
  }
  return {
    name,
    description: getString(record.description) ?? '',
    mcp_server_name: getString(record.mcp_server_name) ?? undefined,
    origin: getString(record.origin) ?? undefined,
    origin_name: getString(record.origin_name) ?? undefined,
    readonly: getBoolean(record.readonly) ?? undefined,
  };
}

function normalizeSkillItem(value: unknown): SkillItemOption | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const name = getString(record?.name);
  if (!name) {
    return null;
  }
  return {
    name,
    description: getString(record.description) ?? '',
    active: getBoolean(record.active) ?? true,
    source_type: getString(record.source_type) ?? undefined,
    plugin_active: getBoolean(record.plugin_active) ?? undefined,
    plugin_display_name: getString(record.plugin_display_name) ?? undefined,
  };
}

function normalizePromptSummary(value: unknown): EditablePrompt | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const promptId = getString(record?.prompt_id);
  const systemPrompt = getString(record?.system_prompt);
  if (!promptId || !systemPrompt) {
    return null;
  }
  return {
    prompt_id: promptId,
    system_prompt: systemPrompt,
    custom_error_message: getString(record.custom_error_message),
    begin_dialogs: getStringArray(record.begin_dialogs),
    tools:
      record.tools === null ? null : getStringArray(record.tools ?? undefined),
    skills:
      record.skills === null
        ? null
        : getStringArray(record.skills ?? undefined),
    folder_id: getString(record.folder_id),
  };
}

async function loadMcpServers() {
  try {
    const response = await mcpApi.list();
    if (response.data.status !== 'ok') {
      emit('error', response.data.message || 'Failed to load MCP servers');
      return;
    }
    const payload = Array.isArray(response.data.data) ? response.data.data : [];
    mcpServers.value = payload
      .map(normalizeMcpServer)
      .filter((server): server is McpServerItem => server !== null);
  } catch (error) {
    emit('error', getApiErrorMessage(error, 'Failed to load MCP servers'));
    mcpServers.value = [];
  }
}

async function loadTools() {
  loadingTools.value = true;
  try {
    const response = await toolApi.list();
    if (response.data.status !== 'ok') {
      emit('error', response.data.message || 'Failed to load tools');
      return;
    }
    const payload = Array.isArray(response.data.data) ? response.data.data : [];
    availableTools.value = payload
      .map(normalizeToolItem)
      .filter((tool): tool is PromptToolItem => tool !== null);
  } catch (error) {
    emit('error', getApiErrorMessage(error, 'Failed to load tools'));
    availableTools.value = [];
  } finally {
    loadingTools.value = false;
  }
}

async function loadSkills() {
  loadingSkills.value = true;
  try {
    const response = await skillApi.list();
    if (response.data.status !== 'ok') {
      emit('error', response.data.message || 'Failed to load skills');
      return;
    }
    const payload = response.data.data;
    const payloadRecord = asRecord(payload);
    let rawSkills: unknown[] = [];
    if (Array.isArray(payload)) {
      rawSkills = payload;
    } else if (Array.isArray(payloadRecord?.skills)) {
      rawSkills = payloadRecord.skills;
    }
    availableSkills.value = rawSkills
      .map(normalizeSkillItem)
      .filter(
        (skill): skill is SkillItemOption =>
          skill !== null &&
          skill.active !== false &&
          skill.plugin_active !== false,
      );
  } catch (error) {
    emit('error', getApiErrorMessage(error, 'Failed to load skills'));
    availableSkills.value = [];
  } finally {
    loadingSkills.value = false;
  }
}

async function loadExistingPromptIds() {
  try {
    const response = await promptApi.list();
    if (response.data.status !== 'ok') {
      existingPromptIds.value = [];
      return;
    }
    const payload = Array.isArray(response.data.data) ? response.data.data : [];
    existingPromptIds.value = payload
      .map(normalizePromptSummary)
      .filter((prompt): prompt is EditablePrompt => prompt !== null)
      .map((prompt) => prompt.prompt_id);
  } catch {
    existingPromptIds.value = [];
  }
}

function buildPromptPayload(): PromptInput {
  return {
    prompt_id: promptForm.prompt_id,
    system_prompt: promptForm.system_prompt,
    custom_error_message: promptForm.custom_error_message || null,
    begin_dialogs: [...promptForm.begin_dialogs],
    tools: cloneStringList(promptForm.tools),
    skills: cloneStringList(promptForm.skills),
    folder_id: promptForm.folder_id,
  };
}

async function savePrompt() {
  if (!formValid.value) {
    return;
  }
  for (let index = 0; index < promptForm.begin_dialogs.length; index += 1) {
    const dialog = promptForm.begin_dialogs[index];
    if (!dialog || dialog.trim() === '') {
      const dialogType =
        index % 2 === 0 ? tm('form.userMessage') : tm('form.assistantMessage');
      emit('error', tm('validation.dialogRequired', { type: dialogType }));
      return;
    }
  }

  saving.value = true;
  try {
    const payload = buildPromptPayload();
    const response = props.editingPrompt
      ? await promptApi.update(payload.prompt_id, {
          system_prompt: payload.system_prompt,
          custom_error_message: payload.custom_error_message,
          begin_dialogs: payload.begin_dialogs,
          tools: payload.tools,
          skills: payload.skills,
          folder_id: payload.folder_id,
        })
      : await promptApi.create(payload);

    if (response.data.status === 'ok') {
      emit('saved', response.data.message || tm('messages.saveSuccess'));
      closeDialog();
    } else {
      emit('error', response.data.message || tm('messages.saveError'));
    }
  } catch (error) {
    emit('error', getApiErrorMessage(error, tm('messages.saveError')));
  } finally {
    saving.value = false;
  }
}

async function deletePrompt() {
  if (!props.editingPrompt) {
    return;
  }
  const confirmed = await askForConfirmationDialog(
    tm('messages.deleteConfirm', {
      id: props.editingPrompt.prompt_id,
    }),
    confirmDialog,
  );
  if (!confirmed) {
    return;
  }

  saving.value = true;
  try {
    const response = await promptApi.delete(props.editingPrompt.prompt_id);
    if (response.data.status === 'ok') {
      emit('deleted', response.data.message || tm('messages.deleteSuccess'));
      closeDialog();
    } else {
      emit('error', response.data.message || tm('messages.deleteError'));
    }
  } catch (error) {
    emit('error', getApiErrorMessage(error, tm('messages.deleteError')));
  } finally {
    saving.value = false;
  }
}

function addDialogPair() {
  promptForm.begin_dialogs.push('', '');
  if (!expandedPanels.value.includes('dialogs')) {
    expandedPanels.value.push('dialogs');
  }
}

function removeDialog(index: number) {
  if (index % 2 === 0 && index + 1 < promptForm.begin_dialogs.length) {
    promptForm.begin_dialogs.splice(index, 2);
  } else if (index % 2 === 1 && index - 1 >= 0) {
    promptForm.begin_dialogs.splice(index - 1, 2);
  }
}

function toggleMcpServer(server: McpServerItem) {
  if (server.tools.length === 0) {
    return;
  }
  if (promptForm.tools === null) {
    promptForm.tools = availableTools.value
      .map((tool) => tool.name)
      .filter((toolName) => !server.tools.includes(toolName));
    toolSelectValue.value = '1';
    return;
  }
  if (!Array.isArray(promptForm.tools)) {
    promptForm.tools = [];
    toolSelectValue.value = '1';
  }

  const allSelected = server.tools.every((toolName) =>
    promptForm.tools?.includes(toolName),
  );
  if (allSelected) {
    promptForm.tools = promptForm.tools.filter(
      (toolName) => !server.tools.includes(toolName),
    );
    return;
  }
  for (const toolName of server.tools) {
    if (!promptForm.tools.includes(toolName)) {
      promptForm.tools.push(toolName);
    }
  }
}

function toggleTool(toolName: string) {
  if (isBuiltinToolName(toolName)) {
    return;
  }
  if (promptForm.tools === null) {
    promptForm.tools = availableTools.value
      .map((tool) => tool.name)
      .filter((name) => name !== toolName);
    toolSelectValue.value = '1';
    return;
  }
  if (Array.isArray(promptForm.tools)) {
    const index = promptForm.tools.indexOf(toolName);
    if (index !== -1) {
      promptForm.tools.splice(index, 1);
    } else {
      promptForm.tools.push(toolName);
    }
    return;
  }
  promptForm.tools = [toolName];
  toolSelectValue.value = '1';
}

function removeTool(toolName: string) {
  if (isBuiltinToolName(toolName)) {
    return;
  }
  if (promptForm.tools === null) {
    promptForm.tools = availableTools.value
      .map((tool) => tool.name)
      .filter((name) => name !== toolName);
    toolSelectValue.value = '1';
    return;
  }
  if (!Array.isArray(promptForm.tools)) {
    return;
  }
  const index = promptForm.tools.indexOf(toolName);
  if (index !== -1) {
    promptForm.tools.splice(index, 1);
  }
}

function toggleSkill(skillName: string) {
  if (promptForm.skills === null) {
    promptForm.skills = availableSkills.value
      .map((skill) => skill.name)
      .filter((name) => name !== skillName);
    skillSelectValue.value = '1';
    return;
  }
  if (Array.isArray(promptForm.skills)) {
    const index = promptForm.skills.indexOf(skillName);
    if (index !== -1) {
      promptForm.skills.splice(index, 1);
    } else {
      promptForm.skills.push(skillName);
    }
    return;
  }
  promptForm.skills = [skillName];
  skillSelectValue.value = '1';
}

function removeSkill(skillName: string) {
  if (promptForm.skills === null) {
    promptForm.skills = availableSkills.value
      .map((skill) => skill.name)
      .filter((name) => name !== skillName);
    skillSelectValue.value = '1';
    return;
  }
  if (!Array.isArray(promptForm.skills)) {
    return;
  }
  const index = promptForm.skills.indexOf(skillName);
  if (index !== -1) {
    promptForm.skills.splice(index, 1);
  }
}

function truncateText(text: string | null | undefined, maxLength: number) {
  if (!text) {
    return '';
  }
  return text.length > maxLength ? `${text.substring(0, maxLength)}...` : text;
}

function isBuiltinTool(tool: PromptToolItem) {
  return tool.origin === 'builtin' || tool.readonly === true;
}

function isBuiltinToolName(toolName: string) {
  return availableTools.value.some(
    (tool) => tool.name === toolName && isBuiltinTool(tool),
  );
}

function getDialogRules(index: number): PromptRule[] {
  const dialogType =
    index % 2 === 0 ? tm('form.userMessage') : tm('form.assistantMessage');
  return [
    (value) =>
      Boolean(value) || tm('validation.dialogRequired', { type: dialogType }),
    (value) =>
      (value.trim().length > 0 && true) ||
      tm('validation.dialogRequired', { type: dialogType }),
  ];
}

function isToolSelected(toolName: string) {
  if (promptForm.tools === null) {
    return true;
  }
  return Array.isArray(promptForm.tools) && promptForm.tools.includes(toolName);
}

function isSkillSelected(skillName: string) {
  if (promptForm.skills === null) {
    return true;
  }
  return (
    Array.isArray(promptForm.skills) && promptForm.skills.includes(skillName)
  );
}

function isServerSelected(server: McpServerItem) {
  if (server.tools.length === 0) {
    return false;
  }
  if (promptForm.tools === null) {
    return true;
  }
  return (
    Array.isArray(promptForm.tools) &&
    server.tools.every((toolName) => promptForm.tools?.includes(toolName))
  );
}
</script>

<style scoped>
.prompt-form-card {
  border-radius: 12px;
  overflow: hidden;
}

.prompt-form__selected-list {
  max-height: 100px;
  overflow-y: auto;
}

.prompt-form-content {
  max-height: min(78vh, 760px);
  overflow-y: auto;
}

.prompt-form-title {
  line-height: 1.3;
}

.prompt-form-actions {
  position: sticky;
  bottom: 0;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.selected-config-area {
  margin-left: 32px;
}

.prompt-form-layout {
  align-items: flex-start;
}

.tools-selection {
  max-height: 300px;
  overflow-y: auto;
}

.builtin-tool-checkbox-placeholder {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
}

.skills-selection {
  max-height: 300px;
  overflow-y: auto;
}

.v-virtual-scroll {
  padding-bottom: 16px;
}

@media (max-width: 600px) {
  .prompt-form-card-mobile {
    border-radius: 0;
  }

  .prompt-form-content {
    max-height: calc(100vh - 128px);
    padding: 16px !important;
  }

  .prompt-basic-col,
  .prompt-panels-col {
    padding-top: 0 !important;
  }

  .prompt-form-title {
    font-size: 1.15rem !important;
    padding: 12px 16px !important;
  }

  .selected-config-area {
    margin-left: 0;
  }

  .tools-selection,
  .skills-selection {
    max-height: 38vh;
  }

  .prompt-form-actions {
    padding: 12px 16px !important;
    gap: 8px;
  }

  .prompt-form-actions .v-btn {
    min-width: 0;
  }
}
</style>

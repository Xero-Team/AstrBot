<template>
  <div class="prompt-preview-card">
    <div class="preview-header">
      <small>{{ tm('promptQuickPreview.title') }}</small>
    </div>

    <div v-if="loading" class="preview-loading">
      <v-progress-circular
        indeterminate
        size="18"
        width="2"
        color="primary"
        class="mr-2"
      />
      <small class="text-grey">{{ tm('promptQuickPreview.loading') }}</small>
    </div>

    <div v-else-if="!modelValue" class="preview-empty">
      <small class="text-grey">{{
        tm('promptQuickPreview.noPromptSelected')
      }}</small>
    </div>

    <div v-else-if="!promptData" class="preview-empty">
      <small class="text-grey">{{
        tm('promptQuickPreview.promptNotFound')
      }}</small>
    </div>

    <div v-else class="preview-content">
      <div class="section-title">
        {{ tm('promptQuickPreview.systemPromptLabel') }}
      </div>
      <pre class="prompt-content">{{ promptData.system_prompt || '' }}</pre>

      <div class="section-title mt-3">
        {{ tm('promptQuickPreview.toolsLabel') }}
      </div>
      <div class="chip-wrap tools-wrap">
        <v-chip
          v-if="promptData.tools === null"
          size="small"
          color="success"
          variant="tonal"
          label
        >
          {{
            tm('promptQuickPreview.allToolsWithCount', {
              count: allToolsCount,
            })
          }}
        </v-chip>
        <div
          v-for="tool in resolvedTools"
          v-else
          :key="tool.name"
          class="tool-item"
        >
          <v-chip
            size="small"
            :color="tool.active === false ? 'warning' : 'primary'"
            variant="outlined"
            label
          >
            {{ tool.name }}
          </v-chip>
          <v-tooltip v-if="tool.active === false" location="top">
            <template #activator="{ props: tooltipProps }">
              <small class="text-warning tool-inactive" v-bind="tooltipProps">
                {{ tm('promptQuickPreview.toolInactive') }}
              </small>
            </template>
            {{ tm('promptQuickPreview.toolInactiveTooltip') }}
          </v-tooltip>
          <small
            v-if="tool.origin || tool.origin_name"
            class="text-grey tool-meta"
          >
            <span v-if="tool.origin"
              >{{ tm('promptQuickPreview.originLabel') }}:
              {{ tool.origin }}</span
            >
            <span v-if="tool.origin_name">
              | {{ tm('promptQuickPreview.originNameLabel') }}:
              {{ tool.origin_name }}</span
            >
          </small>
        </div>
        <small
          v-if="promptData.tools !== null && normalizedTools.length === 0"
          class="text-grey"
        >
          {{ tm('promptQuickPreview.noTools') }}
        </small>
      </div>

      <div class="section-title mt-3">
        {{ tm('promptQuickPreview.skillsLabel') }}
      </div>
      <div class="chip-wrap">
        <v-chip
          v-if="promptData.skills === null"
          size="small"
          color="success"
          variant="tonal"
          label
        >
          {{
            tm('promptQuickPreview.allSkillsWithCount', {
              count: allSkillsCount,
            })
          }}
        </v-chip>
        <div
          v-for="skill in resolvedSkills"
          v-else
          :key="skill.name"
          class="tool-item"
        >
          <v-chip
            size="small"
            :color="skill.plugin_active === false ? 'warning' : 'primary'"
            variant="outlined"
            label
          >
            {{ skill.name }}
          </v-chip>
          <v-tooltip v-if="skill.plugin_active === false" location="top">
            <template #activator="{ props: tooltipProps }">
              <small class="text-warning tool-inactive" v-bind="tooltipProps">
                {{ tm('promptQuickPreview.skillInactive') }}
              </small>
            </template>
            {{ tm('promptQuickPreview.skillInactiveTooltip') }}
          </v-tooltip>
        </div>
        <small
          v-if="promptData.skills !== null && normalizedSkills.length === 0"
          class="text-grey"
        >
          {{ tm('promptQuickPreview.noSkills') }}
        </small>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue';
import { promptApi, skillApi, toolApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
});

const { tm } = useModuleI18n('core.shared');

const loading = ref(false);
const promptData = ref(null);
const toolMetaMap = ref({});
const skillMetaMap = ref({});
const availableSkills = ref([]);

const defaultPromptData = {
  prompt_id: 'default',
  system_prompt: 'You are a helpful and friendly assistant.',
  tools: null,
  skills: null,
};

const normalizedTools = computed(() =>
  Array.isArray(promptData.value?.tools) ? promptData.value.tools : [],
);
const normalizedSkills = computed(() =>
  Array.isArray(promptData.value?.skills) ? promptData.value.skills : [],
);
const allToolsCount = computed(
  () =>
    Object.values(toolMetaMap.value).filter((tool) => tool.origin !== 'builtin')
      .length,
);
const allSkillsCount = computed(() => availableSkills.value.length);
const resolvedTools = computed(() =>
  normalizedTools.value.map((toolName) => {
    const meta = toolMetaMap.value[toolName] || {};
    return {
      name: toolName,
      origin: meta.origin || '',
      origin_name: meta.origin_name || '',
      active: meta.active,
    };
  }),
);
const resolvedSkills = computed(() =>
  normalizedSkills.value.map((skillName) => ({
    name: skillName,
    ...(skillMetaMap.value[skillName] || {}),
  })),
);

async function loadToolsMeta() {
  try {
    const response = await toolApi.list();
    if (response.data?.status === 'ok') {
      const tools = response.data?.data || [];
      const nextMap = {};
      for (const tool of tools) {
        if (!tool?.name) {
          continue;
        }
        nextMap[tool.name] = {
          origin: tool.origin || '',
          origin_name: tool.origin_name || '',
          active: tool.active,
        };
      }
      toolMetaMap.value = nextMap;
    }
  } catch (error) {
    console.error('Failed to load tools metadata:', error);
    toolMetaMap.value = {};
  }
}

async function loadSkillsMeta() {
  try {
    const response = await skillApi.list();
    if (response.data?.status === 'ok') {
      const payload = response.data?.data || [];
      const skills = Array.isArray(payload) ? payload : payload.skills || [];
      const nextMap = {};
      for (const skill of skills) {
        if (skill?.name) {
          nextMap[skill.name] = {
            plugin_active: skill.plugin_active,
          };
        }
      }
      skillMetaMap.value = nextMap;
      availableSkills.value = skills.filter(
        (skill) => skill.active !== false && skill.plugin_active !== false,
      );
    } else {
      availableSkills.value = [];
    }
  } catch (error) {
    console.error('Failed to load skills metadata:', error);
    availableSkills.value = [];
    skillMetaMap.value = {};
  }
}

async function loadPromptPreview(promptId) {
  if (!promptId) {
    promptData.value = null;
    return;
  }

  if (promptId === 'default') {
    promptData.value = defaultPromptData;
    return;
  }

  loading.value = true;
  try {
    const response = await promptApi.list();
    if (response.data?.status === 'ok') {
      const prompts = response.data?.data || [];
      promptData.value =
        prompts.find((item) => item.prompt_id === promptId) || null;
    } else {
      promptData.value = null;
    }
  } catch (error) {
    console.error('Failed to load prompt preview:', error);
    promptData.value = null;
  } finally {
    loading.value = false;
  }
}

function handlePromptSaved() {
  if (props.modelValue) {
    void loadPromptPreview(props.modelValue);
  }
}

watch(
  () => props.modelValue,
  (newValue) => {
    void loadPromptPreview(newValue);
  },
  { immediate: true },
);

void loadToolsMeta();
void loadSkillsMeta();

onMounted(() => {
  window.addEventListener('astrbot:prompt-saved', handlePromptSaved);
});

onBeforeUnmount(() => {
  window.removeEventListener('astrbot:prompt-saved', handlePromptSaved);
});
</script>

<style scoped>
.prompt-preview-card {
  background-color: rgba(var(--v-theme-primary), 0.05);
  border: 1px solid rgba(var(--v-theme-primary), 0.1);
  border-radius: 8px;
  padding: 12px;
}

.preview-header {
  margin-bottom: 8px;
}

.preview-loading,
.preview-empty {
  display: flex;
  align-items: center;
  min-height: 24px;
}

.section-title {
  font-size: 0.75rem;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.85;
}

.prompt-content {
  margin-top: 6px;
  max-height: 180px;
  overflow: auto;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 6px;
  padding: 8px;
}

.chip-wrap {
  display: grid;
  gap: 6px;
  margin-top: 6px;
}

.tools-wrap {
  max-height: 160px;
  overflow: auto;
}

.tool-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.tool-meta {
  font-size: 0.74rem;
}

.tool-inactive {
  font-size: 0.74rem;
}

@media (max-width: 600px) {
  .tools-wrap {
    max-height: 120px;
  }
}
</style>

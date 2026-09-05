<template>
  <div class="capability-loop-selector">
    <v-progress-linear
      v-if="loading"
      indeterminate
      color="primary"
      class="mb-3"
    />
    <v-alert density="compact" variant="tonal" type="info" class="mb-3">
      {{ hint }}
    </v-alert>
    <v-table v-if="capabilities.length" density="compact">
      <thead>
        <tr>
          <th>{{ tm('capabilityLoopSelector.capability') }}</th>
          <th>{{ tm('capabilityLoopSelector.loop') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="capability in capabilities" :key="capability.id">
          <td>{{ capability.label }}</td>
          <td class="capability-loop-selector__control">
            <v-select
              :model-value="routeFor(capability.id)"
              :items="loopOptions"
              density="compact"
              hide-details
              variant="outlined"
              @update:model-value="setRoute(capability.id, $event)"
            />
          </td>
        </tr>
      </tbody>
    </v-table>
    <div v-else-if="!loading" class="text-medium-emphasis text-body-2">
      {{ emptyMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { mcpApi, skillApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

type CapabilityKind = 'mcp' | 'skill';
type LoopMode = 'conversation' | 'work' | 'both';
type RouteKey = 'server_name' | 'skill_name';

interface RouteEntry {
  server_name?: unknown;
  skill_name?: unknown;
  loop?: unknown;
}

interface CapabilityItem {
  id: string;
  label: string;
}

const props = defineProps<{
  kind: CapabilityKind;
  modelValue?: unknown;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: RouteEntry[]];
}>();

const { tm } = useModuleI18n('features/config');
const loading = ref(false);
const capabilities = ref<CapabilityItem[]>([]);

const routeKey = computed<RouteKey>(() =>
  props.kind === 'mcp' ? 'server_name' : 'skill_name',
);
const defaultLoop = computed<LoopMode>(() =>
  props.kind === 'mcp' ? 'work' : 'both',
);
const hint = computed(() =>
  tm(
    props.kind === 'mcp'
      ? 'capabilityLoopSelector.mcpHint'
      : 'capabilityLoopSelector.skillHint',
  ),
);
const emptyMessage = computed(() =>
  tm(
    props.kind === 'mcp'
      ? 'capabilityLoopSelector.emptyMcp'
      : 'capabilityLoopSelector.emptySkill',
  ),
);
const loopOptions = computed(() => [
  { title: tm('capabilityLoopSelector.conversation'), value: 'conversation' },
  { title: tm('capabilityLoopSelector.work'), value: 'work' },
  { title: tm('capabilityLoopSelector.both'), value: 'both' },
]);

function routes(): RouteEntry[] {
  return Array.isArray(props.modelValue)
    ? props.modelValue.filter(
        (route): route is RouteEntry =>
          route !== null && typeof route === 'object',
      )
    : [];
}

function routeFor(capabilityId: string): LoopMode {
  const route = routes().find(
    (item) => item[routeKey.value] === capabilityId,
  )?.loop;
  return route === 'conversation' || route === 'work' || route === 'both'
    ? route
    : defaultLoop.value;
}

function setRoute(capabilityId: string, value: unknown) {
  const loop: LoopMode =
    value === 'conversation' || value === 'work' || value === 'both'
      ? value
      : defaultLoop.value;
  const next = routes().filter((item) => item[routeKey.value] !== capabilityId);
  if (loop !== defaultLoop.value) {
    next.push({ [routeKey.value]: capabilityId, loop });
  }
  emit('update:modelValue', next);
}

function normalizeItems(value: unknown): CapabilityItem[] {
  if (!Array.isArray(value)) return [];
  const items = value
    .filter(
      (item): item is Record<string, unknown> =>
        item !== null && typeof item === 'object',
    )
    .filter((item) => item.active !== false)
    .map((item) => {
      const id = typeof item.name === 'string' ? item.name.trim() : '';
      const description =
        typeof item.description === 'string' ? item.description.trim() : '';
      return {
        id,
        label: description ? `${id} — ${description}` : id,
      };
    })
    .filter((item) => item.id);
  return [...new Map(items.map((item) => [item.id, item])).values()].sort(
    (left, right) => left.label.localeCompare(right.label),
  );
}

function normalizeSkillsPayload(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (value === null || typeof value !== 'object') return [];
  const skills = (value as { skills?: unknown }).skills;
  return Array.isArray(skills) ? skills : [];
}

async function loadCapabilities() {
  loading.value = true;
  try {
    if (props.kind === 'mcp') {
      const response = await mcpApi.list();
      capabilities.value =
        response.data.status === 'ok' ? normalizeItems(response.data.data) : [];
      return;
    }

    const response = await skillApi.list();
    const skills = normalizeSkillsPayload(response.data.data);
    capabilities.value =
      response.data.status === 'ok' ? normalizeItems(skills) : [];
  } catch {
    capabilities.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(loadCapabilities);
</script>

<style scoped>
.capability-loop-selector__control {
  min-width: 220px;
}
</style>

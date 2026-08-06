<template>
  <div class="plugin-loop-selector">
    <v-progress-linear
      v-if="loading"
      indeterminate
      color="primary"
      class="mb-3"
    />
    <v-alert density="compact" variant="tonal" type="info" class="mb-3">
      {{ tm('pluginLoopSelector.hint') }}
    </v-alert>
    <v-table v-if="plugins.length" density="compact">
      <thead>
        <tr>
          <th>{{ tm('pluginLoopSelector.plugin') }}</th>
          <th>{{ tm('pluginLoopSelector.loop') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="plugin in plugins" :key="plugin.id">
          <td>{{ plugin.label }}</td>
          <td class="plugin-loop-selector__control">
            <v-select
              :model-value="routeFor(plugin.id)"
              :items="loopOptions"
              density="compact"
              hide-details
              variant="outlined"
              @update:model-value="setRoute(plugin.id, $event)"
            />
          </td>
        </tr>
      </tbody>
    </v-table>
    <div v-else-if="!loading" class="text-medium-emphasis text-body-2">
      {{ tm('pluginLoopSelector.empty') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { pluginApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

type LoopMode = 'conversation' | 'work' | 'both';

interface PluginRoute {
  plugin_id?: unknown;
  loop?: unknown;
}

interface PluginItem {
  id: string;
  label: string;
}

const props = defineProps<{
  modelValue?: unknown;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: PluginRoute[]];
}>();

const { tm } = useModuleI18n('features/config');
const loading = ref(false);
const plugins = ref<PluginItem[]>([]);

const loopOptions = computed(() => [
  { title: tm('pluginLoopSelector.conversation'), value: 'conversation' },
  { title: tm('pluginLoopSelector.work'), value: 'work' },
  { title: tm('pluginLoopSelector.both'), value: 'both' },
]);

function routes(): PluginRoute[] {
  return Array.isArray(props.modelValue)
    ? props.modelValue.filter(
        (route): route is PluginRoute =>
          route !== null && typeof route === 'object',
      )
    : [];
}

function routeFor(pluginId: string): LoopMode {
  const route = routes().find((item) => item.plugin_id === pluginId)?.loop;
  return route === 'conversation' || route === 'work' ? route : 'both';
}

function setRoute(pluginId: string, value: unknown) {
  const loop: LoopMode =
    value === 'conversation' || value === 'work' ? value : 'both';
  const next = routes().filter((item) => item.plugin_id !== pluginId);
  if (loop !== 'both') {
    next.push({ plugin_id: pluginId, loop });
  }
  emit('update:modelValue', next);
}

async function loadPlugins() {
  loading.value = true;
  try {
    const response = await pluginApi.list();
    if (response.data.status !== 'ok') return;
    plugins.value = (response.data.data || [])
      .filter((plugin) => plugin.activated && !plugin.reserved)
      .map((plugin) => {
        const id = String(plugin.root_dir_name || plugin.name || '');
        return {
          id,
          label: String(plugin.display_name || plugin.name || id),
        };
      })
      .filter((plugin) => plugin.id)
      .sort((left, right) => left.label.localeCompare(right.label));
  } catch {
    plugins.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(loadPlugins);
</script>

<style scoped>
.plugin-loop-selector__control {
  min-width: 220px;
}
</style>

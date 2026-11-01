<template>
  <div class="pypi-mirror">
    <div class="pypi-mirror__header">
      <h5 class="pypi-mirror__title">
        {{ tm('network.pypiMirror.label') }}
      </h5>
      <v-btn
        class="pypi-mirror__test-button"
        size="x-small"
        variant="tonal"
        :loading="testing"
        @click="onTestClick"
      >
        {{ tm('network.pypiMirror.testConnection') }}
        <v-tooltip activator="parent" location="top" max-width="360">
          <div>{{ tm('network.pypiMirror.testTip.serial') }}</div>
          <div>{{ tm('network.pypiMirror.testTip.single') }}</div>
          <div>{{ tm('network.pypiMirror.testTip.parallel') }}</div>
        </v-tooltip>
      </v-btn>
    </div>
    <v-radio-group
      class="mt-2"
      :model-value="activeKey"
      hide-details
      @update:model-value="onSelectionChange"
    >
      <v-radio
        v-for="mirror in mirrors"
        :key="mirror.key"
        color="success"
        :value="mirror.key"
      >
        <template #label>
          <div class="pypi-mirror__option-label">
            <span class="pypi-mirror__name">
              {{ tm(`network.pypiMirror.presets.${mirror.key}`) }}
            </span>
            <span class="pypi-mirror__url">{{ mirror.url }}</span>
            <v-progress-circular
              v-if="testingKeys[mirror.key]"
              indeterminate
              size="14"
              width="2"
              color="primary"
            />
            <v-chip
              v-if="status[mirror.key]"
              :color="status[mirror.key].available ? 'success' : 'error'"
              size="x-small"
            >
              {{
                status[mirror.key].available
                  ? `${status[mirror.key].latency}ms`
                  : tm('network.pypiMirror.unavailable')
              }}
            </v-chip>
            <v-chip v-if="speed[mirror.key]" color="info" size="x-small">
              {{ speed[mirror.key] }}MB/s
            </v-chip>
          </div>
        </template>
      </v-radio>
      <v-radio color="primary" value="custom">
        <template #label>
          <div class="pypi-mirror__option-label">
            <span class="pypi-mirror__name">
              {{ tm('network.pypiMirror.custom') }}
            </span>
            <v-text-field
              class="pypi-mirror__custom-input"
              density="compact"
              :model-value="customUrl"
              variant="outlined"
              :placeholder="tm('network.pypiMirror.customPlaceholder')"
              hide-details
              @update:model-value="onCustomInput"
            />
            <v-progress-circular
              v-if="testingKeys.custom"
              indeterminate
              size="14"
              width="2"
              color="primary"
            />
            <v-chip
              v-if="status.custom"
              :color="status.custom.available ? 'success' : 'error'"
              size="x-small"
            >
              {{
                status.custom.available
                  ? `${status.custom.latency}ms`
                  : tm('network.pypiMirror.unavailable')
              }}
            </v-chip>
            <v-chip v-if="speed.custom" color="info" size="x-small">
              {{ speed.custom }}MB/s
            </v-chip>
          </div>
        </template>
      </v-radio>
    </v-radio-group>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';

import { statsApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

type Mirror = { key: string; url: string };
type MirrorStatus = { available: boolean; latency: number };
type TestStage = 'both' | 'latency' | 'speed';

// The official index is what pip falls back to, so it is listed first like any
// other preset instead of being a separate "no mirror" option.
const OFFICIAL_INDEX_URL = 'https://pypi.org/simple';
// The typed custom URL is remembered separately from the saved config value,
// so it stays visible (and testable) after a reload even while a preset is
// active.
const CUSTOM_STORAGE_KEY = 'selectedPypiMirrorCustom';

const props = withDefaults(defineProps<{ modelValue?: string }>(), {
  modelValue: '',
});
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const { tm } = useModuleI18n('features/settings');

const mirrors: Mirror[] = [
  { key: 'official', url: OFFICIAL_INDEX_URL },
  { key: 'aliyun', url: 'https://mirrors.aliyun.com/pypi/simple' },
  { key: 'tencent', url: 'https://mirrors.cloud.tencent.com/pypi/simple' },
  { key: 'ustc', url: 'https://pypi.mirrors.ustc.edu.cn/simple' },
  { key: 'tsinghua', url: 'https://pypi.tuna.tsinghua.edu.cn/simple' },
];

const activeKey = ref('official');
const customUrl = ref(localStorage.getItem(CUSTOM_STORAGE_KEY) || '');
const status = ref<Record<string, MirrorStatus>>({});
const speed = ref<Record<string, number>>({});
const testing = ref(false);
const testingKeys = ref<Record<string, boolean>>({});

function normalizeUrl(value: unknown): string {
  return String(value || '')
    .trim()
    .replace(/\/+$/, '');
}

function syncFromValue(value: string): void {
  const current = normalizeUrl(value);
  // An empty value means pip uses its default, i.e. the official index.
  const preset = current
    ? mirrors.find((mirror) => normalizeUrl(mirror.url) === current)
    : mirrors[0];
  if (preset) {
    // The custom box keeps whatever is typed in it, so that URL can still be
    // read and tested while it is not the selected source.
    activeKey.value = preset.key;
    return;
  }
  activeKey.value = 'custom';
  customUrl.value = String(value).trim();
}

watch(
  () => props.modelValue,
  (value) => {
    syncFromValue(value);
  },
  { immediate: true },
);

watch(customUrl, (value) => {
  localStorage.setItem(CUSTOM_STORAGE_KEY, value || '');
});

function onSelectionChange(key: string | null): void {
  if (!key) {
    return;
  }
  activeKey.value = key;
  const preset = mirrors.find((mirror) => mirror.key === key);
  if (preset) {
    emit('update:modelValue', preset.url);
    return;
  }
  // Picking the custom option applies the URL already typed, and an empty box
  // leaves the saved source untouched.
  const custom = String(customUrl.value || '').trim();
  if (/^https?:\/\//i.test(custom)) {
    emit('update:modelValue', custom);
  }
}

function onCustomInput(value: string): void {
  customUrl.value = value;
  if (activeKey.value !== 'custom') {
    // Keep the saved source until the option itself is picked.
    return;
  }
  const trimmed = String(value || '').trim();
  if (!trimmed) {
    // Keep the saved value while the field is temporarily empty.
    return;
  }
  emit('update:modelValue', trimmed);
}

async function testMirror(indexUrl: string, statusKey: string): Promise<void> {
  try {
    const response = await statsApi.testPypiIndex({ index_url: indexUrl });
    if (response.status === 200) {
      status.value[statusKey] = {
        available: true,
        latency: Math.round(response.data.data.latency ?? 0),
      };
    } else {
      status.value[statusKey] = { available: false, latency: 0 };
    }
  } catch {
    status.value[statusKey] = { available: false, latency: 0 };
  }
}

// Real download throughput in MB/s, measured by pulling an actual wheel the
// way pip would, instead of timing a round trip.
async function measureMirror(
  indexUrl: string,
  speedKey: string,
): Promise<void> {
  try {
    const response = await statsApi.measurePypiIndexSpeed({
      index_url: indexUrl,
    });
    speed.value[speedKey] =
      response.status === 200 ? Number(response.data.data.speed) || 0 : 0;
  } catch {
    speed.value[speedKey] = 0;
  }
}

// Every source this selector can probe: each preset mirror plus a valid custom
// index URL.
function collectTargets(): Mirror[] {
  const targets = mirrors.map((mirror) => ({
    url: mirror.url,
    key: mirror.key,
  }));

  const customIndex = normalizeUrl(customUrl.value);
  if (/^https?:\/\//i.test(customIndex)) {
    targets.push({ url: customIndex, key: 'custom' });
  }

  return targets;
}

// One source, latency then throughput. A stage argument lets the caller run
// the two stages as separate sweeps across all sources.
async function testTarget(
  target: Mirror,
  stage: TestStage = 'both',
): Promise<void> {
  testingKeys.value[target.key] = true;

  try {
    if (stage !== 'speed') {
      await testMirror(target.url, target.key);
    }
    if (stage !== 'latency') {
      await measureMirror(target.url, target.key);
    }
  } finally {
    testingKeys.value[target.key] = false;
  }
}

type TestClickEvent = MouseEvent | KeyboardEvent;

// Plain click tests every source one after another so results appear source by
// source, Ctrl/Cmd+click re-tests only the selected source, and Shift+click
// runs every source at once.
async function onTestClick(event: TestClickEvent): Promise<void> {
  if (testing.value) {
    return;
  }

  let mode: 'serial' | 'single' | 'parallel' = 'serial';
  if (event.shiftKey) {
    mode = 'parallel';
  } else if (event.ctrlKey || event.metaKey) {
    mode = 'single';
  }

  testing.value = true;

  try {
    if (mode === 'single') {
      // Keep the other results: this only refreshes one source.
      const target = collectTargets().find(
        (item) => item.key === activeKey.value,
      );
      if (target) {
        await testTarget(target);
      }
      return;
    }

    const targets = collectTargets();
    const startIndex = targets.findIndex(
      (item) => item.key === activeKey.value,
    );
    // Start the sweep at the selected source so its result lands first, then
    // keep the listed order of the remaining sources.
    const ordered =
      startIndex > 0
        ? [...targets.slice(startIndex), ...targets.slice(0, startIndex)]
        : targets;
    status.value = {};
    speed.value = {};

    if (mode === 'parallel') {
      // Every latency probe finishes before any download starts, so a
      // saturating speed sample cannot skew a sibling's latency.
      await Promise.all(ordered.map((target) => testTarget(target, 'latency')));
      await Promise.all(ordered.map((target) => testTarget(target, 'speed')));
      return;
    }

    for (const target of ordered) {
      await testTarget(target);
    }
  } finally {
    testing.value = false;
  }
}
</script>

<style scoped>
.pypi-mirror {
  width: 100%;
  min-width: 0;
}

.pypi-mirror__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.pypi-mirror__test-button {
  flex: 0 0 auto;
}

.pypi-mirror__title {
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.4;
}

.pypi-mirror :deep(.v-label) {
  min-width: 0;
  font-size: 0.875rem;
  line-height: 1.35;
  white-space: normal;
}

.pypi-mirror__option-label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
}

.pypi-mirror__name {
  font-weight: 600;
}

.pypi-mirror__url {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.78rem;
  overflow-wrap: anywhere;
}

/* A fixed width keeps the box as long as the longest mirror URL, and stops
   percentage sizing from collapsing it inside the flex label. */
.pypi-mirror__custom-input {
  flex: 0 0 auto;
  width: 272px;
}
</style>

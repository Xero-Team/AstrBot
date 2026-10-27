<template>
  <div
    id="console-wrapper"
    ref="consoleWrapper"
    class="console-displayer-wrapper"
    :class="{ 'console-displayer-wrapper--workspace': props.workspaceMode }"
  >
    <div
      v-if="props.showLevelBtns || props.showSearch"
      class="filter-controls mb-2"
    >
      <v-chip-group
        v-if="props.showLevelBtns && !props.workspaceMode"
        v-model="selectedLevels"
        class="log-level-filters"
        column
        multiple
      >
        <v-chip
          v-for="level in logLevels"
          :key="level"
          :color="getLevelColor(level)"
          filter
          variant="flat"
          size="small"
          :class="[
            'font-weight-medium',
            level === 'DEBUG' || level === 'INFO' ? 'text-black' : 'text-white',
          ]"
        >
          {{ level }}
        </v-chip>
      </v-chip-group>
      <v-btn
        v-if="props.workspaceMode"
        class="filter-toggle-btn"
        size="small"
        :variant="filtersOpen || hasActiveFilters ? 'tonal' : 'text'"
        :aria-expanded="filtersOpen"
        @click="filtersOpen = !filtersOpen"
      >
        <v-icon icon="mdi-filter-variant" size="17" />
        <span>{{ tm('filters.button') }}</span>
        <span v-if="hasActiveFilters" class="filter-status-dot" />
      </v-btn>
      <v-text-field
        v-if="props.showSearch"
        :model-value="searchInput"
        class="log-search-field"
        density="compact"
        variant="solo-filled"
        flat
        hide-details
        single-line
        clearable
        prepend-inner-icon="mdi-magnify"
        :aria-label="tm('search.label')"
        :placeholder="tm('search.placeholder')"
        @update:model-value="searchInput = normalizeTextInput($event)"
      />
      <v-spacer></v-spacer>
      <slot name="header-actions"></slot>
      <v-btn
        :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
        variant="text"
        density="compact"
        class="me-4 fullscreen-btn"
        :aria-label="
          isFullscreen ? tm('fullscreen.exit') : tm('fullscreen.enter')
        "
        @click="toggleFullscreen"
      ></v-btn>
    </div>

    <div class="console-body">
      <aside
        v-if="props.workspaceMode && filtersOpen"
        class="console-filter-panel"
      >
        <div class="console-filter-heading">
          <span>{{ tm('filters.title') }}</span>
          <v-btn
            v-if="hasActiveFilters"
            size="small"
            variant="text"
            :aria-label="tm('filters.reset')"
            @click="resetFilters"
          >
            {{ tm('filters.reset') }}
          </v-btn>
        </div>

        <div class="console-filter-block console-filter-block--first">
          <div class="console-filter-label">{{ tm('filters.level') }}</div>
          <label
            v-for="(level, index) in logLevels"
            :key="level"
            class="console-filter-option"
          >
            <v-checkbox-btn
              v-model="selectedLevels"
              :value="index"
              density="compact"
              hide-details
            />
            <span
              class="level-indicator"
              :class="`level-indicator--${level.toLowerCase()}`"
            />
            <span>{{ level }}</span>
          </label>
        </div>

        <div class="console-filter-block">
          <div class="console-filter-label">{{ tm('filters.source') }}</div>
          <v-radio-group
            v-model="selectedSource"
            hide-details
            density="compact"
          >
            <v-radio :label="tm('filters.allSources')" value="all" />
            <v-radio :label="tm('filters.core')" value="core" />
            <v-radio :label="tm('filters.plugins')" value="plugin" />
          </v-radio-group>
        </div>

        <div class="console-filter-block">
          <div class="console-filter-label">{{ tm('filters.plugin') }}</div>
          <v-select
            v-model="selectedPlugin"
            :items="pluginOptions"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
            clearable
            item-title="title"
            item-value="value"
            :disabled="selectedSource === 'core' || pluginOptions.length === 0"
            :placeholder="tm('filters.pluginsInLogs')"
          >
            <template #item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="item.subtitle" />
            </template>
          </v-select>
          <div class="console-filter-hint">
            {{ tm('filters.pluginsInLogsHint') }}
          </div>
        </div>

        <div class="console-filter-block console-filter-block--last">
          <div class="console-filter-label">{{ tm('filters.platform') }}</div>
          <v-select
            v-model="selectedPlatform"
            :items="platformOptions"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
            clearable
            item-title="title"
            item-value="value"
            :placeholder="tm('filters.allPlatforms')"
          />
        </div>
      </aside>

      <div
        ref="termElement"
        class="console-term"
        :style="{ '--console-log-font-size': `${props.fontSize}px` }"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { logApi, pluginApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useCommonStore } from '@/stores/common';
import { normalizeTextInput } from '@/utils/inputValue';
import { EventSourcePolyfill } from 'event-source-polyfill';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

interface ConsoleLogEntry {
  time: number;
  data: string;
  level: string;
  source?: string;
  plugin_name?: string | null;
  platform_id?: string | null;
  platform_type?: string | null;
  category?: string;
  [key: string]: unknown;
}

type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
type SourceFilter = 'all' | 'core' | 'plugin';

const props = withDefaults(
  defineProps<{
    showLevelBtns?: boolean;
    autoScroll?: boolean;
    hideUserChat?: boolean;
    workspaceMode?: boolean;
    showSearch?: boolean;
    fontSize?: number;
  }>(),
  {
    showLevelBtns: true,
    autoScroll: true,
    hideUserChat: true,
    workspaceMode: false,
    showSearch: false,
    fontSize: 12,
  },
);

const { tm } = useModuleI18n('features/logs');
const commonStore = useCommonStore();
const consoleWrapper = ref<HTMLElement | null>(null);
const termElement = ref<HTMLDivElement | null>(null);
const isFullscreen = ref(false);
const filtersOpen = ref(false);
const selectedLevels = ref<number[]>([0, 1, 2, 3, 4]);
const selectedSource = ref<SourceFilter>('all');
const selectedPlugin = ref<string | null>(null);
const selectedPlatform = ref<string | null>(null);
const pluginDisplayNames = ref<Record<string, string>>({});
const localLogCache = ref<ConsoleLogEntry[]>([]);
const eventSource = ref<EventSourcePolyfill | null>(null);
const retryTimer = ref<ReturnType<typeof window.setTimeout> | null>(null);
const retryAttempts = ref(0);
const lastEventId = ref<string | null>(null);
const searchInput = ref('');
const searchKeyword = ref('');
const searchTimer = ref<ReturnType<typeof window.setTimeout> | null>(null);
let unmounted = false;

const hasActiveFilters = computed(
  () =>
    selectedSource.value !== 'all' ||
    Boolean(selectedPlugin.value) ||
    Boolean(selectedPlatform.value),
);

const pluginOptions = computed(() => {
  const names = Array.from(
    new Set(
      localLogCache.value
        .map((log) => log.plugin_name)
        .filter(
          (name): name is string => typeof name === 'string' && Boolean(name),
        ),
    ),
  );
  return names
    .map((value) => ({
      title: pluginDisplayNames.value[value] || value,
      subtitle: value,
      value,
    }))
    .sort(
      (a, b) =>
        a.title.localeCompare(b.title) || a.value.localeCompare(b.value),
    );
});

const platformOptions = computed(() => {
  const platforms = new Map<string, { title: string; value: string }>();
  let hasUnscoped = false;
  for (const log of localLogCache.value) {
    if (!log.platform_id) {
      hasUnscoped = true;
      continue;
    }
    const type = log.platform_type ? ` (${log.platform_type})` : '';
    platforms.set(log.platform_id, {
      title: `${log.platform_id}${type}`,
      value: log.platform_id,
    });
  }
  const options = Array.from(platforms.values()).sort((a, b) =>
    a.title.localeCompare(b.title),
  );
  if (hasUnscoped) {
    options.unshift({
      title: tm('filters.unscopedPlatform'),
      value: '__unscoped__',
    });
  }
  return options;
});

const logColorAnsiMap: Record<string, string> = {
  '\u001b[1;34m': 'color: #6cb6d9; font-weight: bold;',
  '\u001b[1;36m': 'color: #72c4cc; font-weight: bold;',
  '\u001b[1;33m': 'color: #d4b95e; font-weight: bold;',
  '\u001b[31m': 'color: #d46a6a;',
  '\u001b[1;31m': 'color: #e06060; font-weight: bold;',
  '\u001b[0m': 'color: inherit; font-weight: normal;',
  '\u001b[32m': 'color: #6cc070;',
  default: 'color: #c8c8c8;',
};

const logLevels: LogLevel[] = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];
const levelColors: Record<LogLevel, string> = {
  DEBUG: 'grey',
  INFO: 'blue-lighten-3',
  WARNING: 'amber',
  ERROR: 'red',
  CRITICAL: 'purple',
};

const maxRetryAttempts = 10;
const baseRetryDelay = 1000;
const ANSI_ESCAPE_PATTERN = new RegExp(
  `${String.fromCharCode(27)}\\[[0-9;]*m`,
  'g',
);

function closeEventSource(): void {
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }
}

function clearRetryTimer(): void {
  if (retryTimer.value !== null) {
    clearTimeout(retryTimer.value);
    retryTimer.value = null;
  }
}

function normalizeLogEntry(raw: unknown): ConsoleLogEntry | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const candidate = raw as Record<string, unknown>;
  const data = candidate.data;
  const level = candidate.level;
  const time = candidate.time;
  return {
    ...candidate,
    data: typeof data === 'string' ? data : String(data ?? ''),
    level: typeof level === 'string' ? level : 'INFO',
    time: typeof time === 'number' ? time : Number(time ?? Date.now()),
  };
}

function getLevelColor(level: LogLevel): string {
  return levelColors[level] || 'grey';
}

function isLevelSelected(level: string): boolean {
  return selectedLevels.value.some((index) => logLevels[index] === level);
}

function matchesSource(log: ConsoleLogEntry): boolean {
  if (selectedSource.value === 'all') {
    return true;
  }
  return (log.source || 'core') === selectedSource.value;
}

function matchesPlugin(log: ConsoleLogEntry): boolean {
  return !selectedPlugin.value || log.plugin_name === selectedPlugin.value;
}

function matchesPlatform(log: ConsoleLogEntry): boolean {
  if (!selectedPlatform.value) {
    return true;
  }
  if (selectedPlatform.value === '__unscoped__') {
    return !log.platform_id;
  }
  return log.platform_id === selectedPlatform.value;
}

function resetFilters(): void {
  selectedLevels.value = logLevels.map((_, index) => index);
  selectedSource.value = 'all';
  selectedPlugin.value = null;
  selectedPlatform.value = null;
  refreshDisplay();
}

function isVisible(log: ConsoleLogEntry): boolean {
  return (
    isLevelSelected(log.level) &&
    !(props.hideUserChat && log.category === 'user_chat') &&
    matchesSource(log) &&
    matchesPlugin(log) &&
    matchesPlatform(log) &&
    matchesKeyword(log)
  );
}

function matchesKeyword(log: ConsoleLogEntry): boolean {
  if (!searchKeyword.value) {
    return true;
  }
  const text = log.data.replace(ANSI_ESCAPE_PATTERN, '').toLowerCase();
  return text.includes(searchKeyword.value.toLowerCase());
}

function appendHighlightedText(element: HTMLElement, text: string): void {
  const keyword = searchKeyword.value;
  const cleanText = text.replace(ANSI_ESCAPE_PATTERN, '');
  if (!keyword || !cleanText) {
    element.textContent = cleanText;
    return;
  }

  const lowerText = cleanText.toLowerCase();
  const lowerKeyword = keyword.toLowerCase();
  let cursor = 0;
  let index = lowerText.indexOf(lowerKeyword);
  while (index !== -1) {
    if (index > cursor) {
      element.appendChild(
        document.createTextNode(cleanText.slice(cursor, index)),
      );
    }
    const highlight = document.createElement('span');
    highlight.className = 'console-log-highlight';
    highlight.textContent = cleanText.slice(index, index + keyword.length);
    element.appendChild(highlight);
    cursor = index + keyword.length;
    index = lowerText.indexOf(lowerKeyword, cursor);
  }
  if (cursor < cleanText.length) {
    element.appendChild(document.createTextNode(cleanText.slice(cursor)));
  }
}

function appendLogContent(element: HTMLPreElement, log: string): void {
  const levelPattern =
    /\[(DEBG|INFO|WARN|ERRO|CRIT|DEBUG|WARNING|ERROR|CRITICAL)\]/;
  const levelMatch = levelPattern.exec(log);
  if (levelMatch?.index === undefined) {
    appendHighlightedText(element, log);
    return;
  }

  const levelStart = levelMatch.index;
  const levelEnd = levelStart + levelMatch[0].length;
  const prefix = log.slice(0, levelStart).trimEnd();
  const message = log.slice(levelEnd).trimStart();

  const prefixSpan = document.createElement('span');
  prefixSpan.className = 'console-log-prefix';
  appendHighlightedText(prefixSpan, prefix);

  const levelSpan = document.createElement('span');
  levelSpan.className = 'console-log-level';
  appendHighlightedText(levelSpan, levelMatch[0]);

  const messageSpan = document.createElement('span');
  messageSpan.className = 'console-log-message';
  appendHighlightedText(messageSpan, message);

  element.classList.add('console-log-line--structured');
  element.appendChild(prefixSpan);
  element.appendChild(levelSpan);
  element.appendChild(messageSpan);
}

function buildLogElement(log: string): HTMLPreElement {
  const span = document.createElement('pre');
  let normalizedLog = log;
  let style = logColorAnsiMap.default;
  for (const [ansiPrefix, ansiStyle] of Object.entries(logColorAnsiMap)) {
    if (ansiPrefix !== 'default' && normalizedLog.startsWith(ansiPrefix)) {
      style = ansiStyle;
      normalizedLog = normalizedLog
        .replace(ansiPrefix, '')
        .replace('\u001b[0m', '');
      break;
    }
  }

  span.style.cssText = style;
  span.classList.add('console-log-line', 'fade-in');
  appendLogContent(span, normalizedLog);
  return span;
}

function appendLogBatch(logs: string[]): void {
  const target = termElement.value;
  if (!target || logs.length === 0) {
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const log of logs) {
    fragment.appendChild(buildLogElement(log));
  }
  target.appendChild(fragment);
  if (props.autoScroll) {
    target.scrollTop = target.scrollHeight;
  }
}

function refreshDisplay(): void {
  const target = termElement.value;
  if (!target) {
    return;
  }
  target.replaceChildren();
  appendLogBatch(
    localLogCache.value.filter(isVisible).map((logItem) => logItem.data),
  );
}

function processNewLogs(newLogs: unknown[]): void {
  if (newLogs.length === 0) {
    return;
  }

  let hasUpdate = false;
  const visibleLogs: string[] = [];

  for (const rawLog of newLogs) {
    const log = normalizeLogEntry(rawLog);
    if (!log) {
      continue;
    }
    const exists = localLogCache.value.some(
      (existing) =>
        existing.time === log.time &&
        existing.data === log.data &&
        existing.level === log.level,
    );

    if (!exists) {
      localLogCache.value.push(log);
      hasUpdate = true;

      if (isVisible(log)) {
        visibleLogs.push(log.data);
      }
    }
  }

  if (!hasUpdate) {
    return;
  }

  appendLogBatch(visibleLogs);

  localLogCache.value.sort((a, b) => a.time - b.time);

  const maxSize = commonStore.log_cache_max_len || 200;
  if (localLogCache.value.length > maxSize) {
    localLogCache.value.splice(0, localLogCache.value.length - maxSize);
  }
}

async function fetchLogHistory(): Promise<void> {
  try {
    const res = await logApi.history();
    const logs = Array.isArray(res.data.data.logs) ? res.data.data.logs : [];
    if (logs.length > 0) {
      processNewLogs(logs);
    }
  } catch (error) {
    console.error('Failed to fetch log history:', error);
  }
}

async function fetchPluginDisplayNames(): Promise<void> {
  try {
    const res = await pluginApi.list();
    const displayNames: Record<string, string> = {};
    for (const plugin of res.data?.data || []) {
      const name = String(plugin?.name || '').trim();
      const displayName = String(plugin?.display_name || '').trim();
      if (name && displayName) {
        displayNames[name] = displayName;
      }
    }
    pluginDisplayNames.value = displayNames;
  } catch (error) {
    console.warn('Failed to load plugin display names:', error);
  }
}

function connectSSE(): void {
  if (unmounted) {
    return;
  }
  closeEventSource();

  console.log(`正在连接日志流... (尝试次数: ${retryAttempts.value})`);

  const token = localStorage.getItem('token');

  eventSource.value = new EventSourcePolyfill(logApi.liveUrl(), {
    headers: {
      Authorization: token ? `Bearer ${token}` : '',
    },
    heartbeatTimeout: 300000,
    withCredentials: true,
  });

  eventSource.value.onopen = () => {
    console.log('日志流连接成功！');
    retryAttempts.value = 0;

    if (!lastEventId.value) {
      void fetchLogHistory();
    }
  };

  eventSource.value.onmessage = (event: MessageEvent<string>) => {
    try {
      if (event.lastEventId) {
        lastEventId.value = event.lastEventId;
      }

      processNewLogs([JSON.parse(event.data)]);
    } catch (error) {
      console.error('解析日志失败:', error);
    }
  };

  eventSource.value.onerror = (error: unknown) => {
    const eventError = error as { status?: number };
    if (eventError.status === 401) {
      console.error('鉴权失败 (401)，可能是 Token 过期了。');
    } else {
      console.warn('日志流连接错误:', error);
    }

    closeEventSource();

    if (retryAttempts.value >= maxRetryAttempts) {
      console.error('❌ 已达到最大重试次数，停止重连。请刷新页面重试。');
      return;
    }

    const delay = Math.min(
      baseRetryDelay * Math.pow(2, retryAttempts.value),
      30000,
    );

    console.log(`⏳ ${delay}ms 后尝试第 ${retryAttempts.value + 1} 次重连...`);

    clearRetryTimer();
    retryTimer.value = window.setTimeout(async () => {
      retryAttempts.value += 1;

      if (!lastEventId.value) {
        await fetchLogHistory();
      }

      if (unmounted) {
        return;
      }

      connectSSE();
    }, delay);
  };
}

function toggleFullscreen(): void {
  const container = consoleWrapper.value;
  if (!container) {
    return;
  }
  if (!document.fullscreenElement) {
    container.requestFullscreen().catch((error: unknown) => {
      const candidate = error as { message?: string };
      console.error(
        `Error attempting to enable full-screen mode: ${candidate.message || error}`,
      );
    });
    return;
  }
  void document.exitFullscreen();
}

function handleFullscreenChange(): void {
  isFullscreen.value = Boolean(document.fullscreenElement);
}

watch(
  selectedLevels,
  () => {
    refreshDisplay();
  },
  { deep: true },
);

watch(selectedSource, (value) => {
  if (value === 'core') {
    selectedPlugin.value = null;
  }
  refreshDisplay();
});

watch(selectedPlugin, () => {
  refreshDisplay();
});

watch(selectedPlatform, () => {
  refreshDisplay();
});

watch(searchInput, (value) => {
  if (searchTimer.value !== null) {
    clearTimeout(searchTimer.value);
  }
  searchTimer.value = window.setTimeout(() => {
    searchTimer.value = null;
    const keyword = value.trim();
    if (keyword !== searchKeyword.value) {
      searchKeyword.value = keyword;
      refreshDisplay();
    }
  }, 250);
});

onMounted(async () => {
  await fetchLogHistory();
  if (unmounted) {
    return;
  }
  if (props.workspaceMode) {
    await fetchPluginDisplayNames();
    if (unmounted) {
      return;
    }
  }
  connectSSE();
  document.addEventListener('fullscreenchange', handleFullscreenChange);
});

onBeforeUnmount(() => {
  // Pending initialization and reconnect requests may finish after teardown.
  unmounted = true;
  document.removeEventListener('fullscreenchange', handleFullscreenChange);
  closeEventSource();
  clearRetryTimer();
  if (searchTimer.value !== null) {
    clearTimeout(searchTimer.value);
    searchTimer.value = null;
  }
  retryAttempts.value = 0;
});
</script>

<style scoped>
.console-displayer-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.console-displayer-wrapper:fullscreen {
  --v-theme-on-surface: 255, 255, 255;
  background-color: #1e1e1e;
  color: #fff;
  padding: 20px;
}

.console-displayer-wrapper:fullscreen :deep(.console-pip-dialog) {
  border-color: rgb(255 255 255 / 16%);
  background-color: #1e1e1e;
  color: #fff;
}

.console-displayer-wrapper:fullscreen :deep(.console-pip-dialog .v-field) {
  --v-theme-surface: 36, 36, 36;
  --v-theme-on-surface: 255, 255, 255;
}

.console-displayer-wrapper:fullscreen :deep(.v-switch__track) {
  --v-theme-surface-variant: 163, 163, 163;
}

.console-displayer-wrapper:fullscreen .log-search-field :deep(.v-field) {
  --v-theme-surface: 36, 36, 36;
  --v-theme-surface-variant: 36, 36, 36;
  --v-theme-on-surface: 255, 255, 255;
}

.filter-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.console-body {
  display: flex;
  flex: 1 1 auto;
  gap: 12px;
  min-height: 0;
}

.filter-toggle-btn {
  flex: 0 0 auto;
  text-transform: none;
}

.filter-status-dot {
  background: rgb(var(--v-theme-primary));
  border-radius: 50%;
  display: inline-block;
  height: 6px;
  margin-inline-start: 6px;
  width: 6px;
}

.console-filter-panel {
  background: rgba(var(--v-theme-surface), 0.6);
  border-radius: 12px;
  display: flex;
  flex: 0 0 240px;
  flex-direction: column;
  gap: 4px;
  max-height: 100%;
  overflow-y: auto;
  padding: 12px;
}

.console-filter-heading {
  align-items: center;
  display: flex;
  font-size: 0.8rem;
  font-weight: 600;
  justify-content: space-between;
  margin-bottom: 4px;
}

.console-filter-block {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 8px 0;
}

.console-filter-block--first {
  border-top: 0;
}

.console-filter-block--last {
  padding-bottom: 0;
}

.console-filter-label {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: var(--astrbot-meta-size);
  font-weight: 600;
  margin-bottom: 4px;
}

.console-filter-hint {
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: var(--astrbot-meta-size);
  line-height: 1.45;
  margin-top: 6px;
}

.console-filter-option {
  align-items: center;
  display: flex;
  gap: 6px;
  padding: 2px 0;
}

.level-indicator {
  border-radius: 50%;
  display: inline-block;
  height: 9px;
  width: 9px;
}

.level-indicator--debug {
  background: #9aa0a6;
}

.level-indicator--info {
  background: #67b7dc;
}

.level-indicator--warning {
  background: #d4ad45;
}

.level-indicator--error {
  background: #df6262;
}

.level-indicator--critical {
  background: #bb68d5;
}

.log-search-field {
  flex: 0 1 260px;
  max-width: 260px;
  min-width: 160px;
}

.console-displayer-wrapper--workspace {
  background: var(--console-workspace-card, #f5f6f7);
  border-radius: 16px;
  overflow: hidden;
  padding: 12px;
}

.console-term {
  background-color: #1e1e1e;
  border-radius: 8px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: auto;
  padding: 16px;
}

.console-displayer-wrapper--workspace .filter-controls {
  flex: 0 0 auto;
  gap: 8px 12px;
  margin-bottom: 10px !important;
  min-height: 42px;
  padding: 0 2px;
}

.console-displayer-wrapper--workspace .log-level-filters {
  flex: 0 1 auto;
  min-width: 0;
}

.console-displayer-wrapper--workspace .console-term {
  background: #17191c;
  border-radius: 12px;
  flex: 1 1 auto;
  min-height: 0;
  padding: 14px;
}

.console-displayer-wrapper--workspace .fullscreen-btn {
  margin-inline-end: 0 !important;
}

.fullscreen-btn {
  color: rgba(255, 255, 255, 0.7) !important; /* 提高在深色背景下的对比度 */
}

:deep(.console-log-line) {
  display: block;
  margin: 0 0 2px;
  font-family: var(--astrbot-font-mono);
  font-size: var(--console-log-font-size, 12px);
  white-space: pre-wrap;
}

:deep(.console-log-line--structured) {
  display: grid;
  grid-template-columns: max-content max-content minmax(0, 1fr);
  column-gap: 8px;
  align-items: start;
  white-space: normal;
}

:deep(.console-log-prefix),
:deep(.console-log-level),
:deep(.console-log-message) {
  min-width: 0;
  white-space: pre-wrap;
}

:deep(.console-log-level) {
  font-variant-numeric: tabular-nums;
}

:deep(.console-log-message) {
  overflow-wrap: anywhere;
}

:deep(.console-log-highlight) {
  background: rgba(255, 213, 79, 0.35);
  border-radius: 2px;
}

@media (max-width: 768px) {
  .console-displayer-wrapper--workspace {
    border-radius: 14px;
    padding: 10px;
  }

  .console-displayer-wrapper--workspace .filter-controls {
    align-items: flex-start;
    gap: 6px;
    padding: 0;
  }

  .console-displayer-wrapper--workspace .filter-controls > .v-spacer {
    display: none;
  }

  .console-displayer-wrapper--workspace .log-level-filters {
    flex: 1 1 calc(100% - 38px);
    order: 1;
  }

  .console-displayer-wrapper--workspace .log-search-field {
    flex: 1 1 100%;
    max-width: none;
    order: 3;
  }

  .console-displayer-wrapper--workspace :deep(.console-header-actions) {
    flex: 1 1 100%;
    order: 4;
  }

  .console-displayer-wrapper--workspace .fullscreen-btn {
    order: 2;
  }

  .console-body {
    flex-direction: column;
  }

  .console-filter-panel {
    flex: 0 0 auto;
    max-height: 42vh;
  }

  :deep(.console-log-line--structured) {
    grid-template-columns: 1fr;
  }
  :deep(.console-log-prefix:empty),
  :deep(.console-log-level:empty) {
    display: none;
  }
}

:deep(.fade-in) {
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}
</style>

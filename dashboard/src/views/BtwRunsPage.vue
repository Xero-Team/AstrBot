<template>
  <div class="btw-runs-page">
    <header class="btw-runs-page__header">
      <div>
        <h1 class="btw-runs-page__title">{{ tm('btwRuns.title') }}</h1>
        <p class="btw-runs-page__subtitle">{{ tm('btwRuns.subtitle') }}</p>
      </div>
      <v-btn
        class="btw-runs-page__refresh"
        color="primary"
        variant="tonal"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="load"
      >
        {{ tm('btwRuns.refresh') }}
      </v-btn>
    </header>

    <v-alert
      v-if="loadError"
      class="mb-4"
      density="compact"
      variant="tonal"
      type="error"
    >
      {{ tm('btwRuns.loadError') }}
      <template #append>
        <v-btn size="small" variant="text" @click="load">
          {{ tm('btwRuns.retry') }}
        </v-btn>
      </template>
    </v-alert>

    <v-progress-linear
      v-if="loading && !sessions.length"
      class="mb-4"
      color="primary"
      indeterminate
    />

    <v-alert
      v-if="loaded && !sessions.length && !loadError"
      class="btw-runs-page__empty"
      density="compact"
      variant="tonal"
      type="info"
    >
      <div>{{ tm('btwRuns.empty') }}</div>
      <div class="text-body-2 mt-1">{{ tm('btwRuns.emptyHint') }}</div>
    </v-alert>

    <v-card
      v-for="session in sessions"
      :key="session.id"
      class="btw-runs-page__session mb-4"
      variant="outlined"
    >
      <v-card-title class="d-flex flex-wrap align-center ga-2">
        <v-chip
          class="btw-runs-page__session-status"
          :color="statusColor(session.status)"
          size="small"
          variant="tonal"
        >
          {{ statusLabel(session.status) }}
        </v-chip>
        <span class="text-body-1">{{ session.request }}</span>
        <v-spacer />
        <span class="text-caption text-medium-emphasis">
          {{ formatDate(session.updated_at) }}
        </span>
      </v-card-title>

      <v-card-subtitle class="btw-runs-page__session-meta">
        {{ tm('btwRuns.profile') }}: {{ session.config_id }}
        <span class="mx-2">·</span>
        {{ tm('btwRuns.origin') }}: {{ session.origin }}
      </v-card-subtitle>

      <v-card-text>
        <v-alert
          v-if="session.error"
          class="mb-3"
          density="compact"
          variant="tonal"
          type="error"
        >
          {{ session.error }}
        </v-alert>

        <div v-if="session.artifacts.length" class="mb-3">
          <div class="text-subtitle-2">{{ tm('btwRuns.artifacts') }}</div>
          <ul class="btw-runs-page__artifacts">
            <li v-for="artifact in session.artifacts" :key="artifact">
              <code>{{ artifact }}</code>
            </li>
          </ul>
        </div>

        <v-alert
          v-if="!session.delegations.length"
          density="compact"
          variant="tonal"
          type="info"
        >
          {{ tm('btwRuns.noDelegations') }}
        </v-alert>

        <v-card
          v-for="delegation in session.delegations"
          :key="delegation.run_id"
          class="btw-runs-page__delegation mb-3"
          variant="tonal"
        >
          <v-card-title class="d-flex flex-wrap align-center ga-2">
            <v-icon icon="mdi-console-line" size="small" />
            <span>{{ delegation.agent_name || delegation.agent_id }}</span>
            <v-chip
              class="btw-runs-page__delegation-status"
              :color="statusColor(delegation.status)"
              size="x-small"
              variant="flat"
            >
              {{ statusLabel(delegation.status) }}
            </v-chip>
            <v-spacer />
            <span class="text-caption">{{ delegation.agent_type }}</span>
          </v-card-title>

          <v-card-text>
            <div class="btw-runs-page__facts">
              <span
                ><strong>{{ tm('btwRuns.latestAction') }}:</strong>
                {{ delegation.latest_action }}</span
              >
              <span
                ><strong>{{ tm('btwRuns.events') }}:</strong>
                {{ delegation.event_count }}</span
              >
              <span
                ><strong>{{ tm('btwRuns.toolCalls') }}:</strong>
                {{ delegation.tool_call_count }}</span
              >
              <span v-if="delegation.exit_code !== null">
                <strong>{{ tm('btwRuns.exitCode') }}:</strong>
                {{ delegation.exit_code }}
              </span>
              <span
                ><strong>{{ tm('btwRuns.runId') }}:</strong>
                <code>{{ delegation.run_id }}</code></span
              >
            </div>

            <div v-if="delegation.detail" class="text-body-2 mt-2">
              {{ delegation.detail }}
            </div>

            <div
              v-if="Object.keys(delegation.usage).length"
              class="text-caption mt-2"
            >
              {{ tm('btwRuns.usage') }}: {{ usageText(delegation.usage) }}
            </div>

            <v-btn
              class="btw-runs-page__timeline-toggle mt-2"
              size="small"
              variant="text"
              :prepend-icon="
                timelineOpen.has(delegation.run_id)
                  ? 'mdi-chevron-up'
                  : 'mdi-chevron-down'
              "
              @click="toggleTimeline(delegation.run_id)"
            >
              {{
                timelineOpen.has(delegation.run_id)
                  ? tm('btwRuns.hideTimeline')
                  : tm('btwRuns.showTimeline')
              }}
            </v-btn>

            <v-expand-transition>
              <div v-if="timelineOpen.has(delegation.run_id)">
                <v-alert
                  v-if="!delegation.recent_events.length"
                  density="compact"
                  variant="tonal"
                  type="info"
                >
                  {{ tm('btwRuns.noEvents') }}
                </v-alert>
                <ol class="btw-runs-page__timeline">
                  <li
                    v-for="event in delegation.recent_events"
                    :key="`${delegation.run_id}-${event.timestamp}-${event.type}-${event.summary}`"
                  >
                    <span class="text-caption text-medium-emphasis">
                      {{ formatDate(event.timestamp) }}
                    </span>
                    <v-chip size="x-small" variant="tonal" class="mx-2">
                      {{ event.type }}
                    </v-chip>
                    <span>{{ event.summary }}</span>
                  </li>
                </ol>
              </div>
            </v-expand-transition>
          </v-card-text>
        </v-card>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { btwApi, type BtwWorkSession } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

defineOptions({ name: 'BtwRunsPage' });

const { tm } = useModuleI18n('features/config');
const sessions = ref<BtwWorkSession[]>([]);
const loading = ref(false);
const loaded = ref(false);
const loadError = ref(false);
const timelineOpen = ref(new Set<string>());
let refreshTimer: number | undefined;

const hasActiveRun = computed(() =>
  sessions.value.some(
    (session) =>
      session.status === 'pending' ||
      session.status === 'running' ||
      session.delegations.some((delegation) => delegation.status === 'running'),
  ),
);

function statusLabel(status: string) {
  return tm(`btwRuns.status.${status}`);
}

function statusColor(status: string) {
  if (status === 'completed') return 'success';
  if (status === 'failed' || status === 'timed_out') return 'error';
  if (status === 'cancelled') return 'warning';
  if (status === 'running' || status === 'pending') return 'primary';
  return 'grey';
}

function formatDate(value: string) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function usageText(usage: Record<string, number>) {
  return Object.entries(usage)
    .map(([key, value]) => `${key}=${value}`)
    .join(', ');
}

function toggleTimeline(runId: string) {
  const next = new Set(timelineOpen.value);
  if (next.has(runId)) next.delete(runId);
  else next.add(runId);
  timelineOpen.value = next;
}

async function load() {
  if (loading.value) return;
  loading.value = true;
  try {
    const response = await btwApi.listWorkSessions();
    sessions.value = response.data.data.sessions;
    loadError.value = false;
  } catch {
    loadError.value = true;
  } finally {
    loading.value = false;
    loaded.value = true;
  }
}

function scheduleRefresh() {
  window.clearInterval(refreshTimer);
  refreshTimer = window.setInterval(() => {
    if (hasActiveRun.value) void load();
  }, 3000);
}

onMounted(() => {
  void load();
  scheduleRefresh();
});

onUnmounted(() => {
  window.clearInterval(refreshTimer);
});
</script>

<style scoped>
.btw-runs-page {
  padding: 16px;
}

.btw-runs-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.btw-runs-page__title {
  font-size: 1.25rem;
  font-weight: 600;
}

.btw-runs-page__subtitle {
  margin-top: 4px;
  opacity: 0.7;
  max-width: 72ch;
}

.btw-runs-page__session-meta {
  opacity: 0.8;
}

.btw-runs-page__delegation {
  background: rgba(var(--v-theme-surface-variant), 0.35);
}

.btw-runs-page__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  font-size: 0.875rem;
}

.btw-runs-page__artifacts {
  margin: 4px 0 0;
  padding-left: 20px;
}

.btw-runs-page__timeline {
  margin: 8px 0 0;
  padding-left: 20px;
}

.btw-runs-page__timeline li {
  margin-bottom: 8px;
  overflow-wrap: anywhere;
}
</style>

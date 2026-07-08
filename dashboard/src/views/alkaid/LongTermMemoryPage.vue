<template>
  <div class="memory-page">
    <v-row>
      <v-col cols="12" md="3">
        <v-card>
          <v-card-title>{{ tm('stats.title') }}</v-card-title>
          <v-card-text>
            <div class="stat-line">
              <span>{{ tm('stats.activeFacts') }}</span>
              <strong>{{ stats.facts ?? 0 }}</strong>
            </div>
            <div class="stat-line">
              <span>{{ tm('stats.deletedFacts') }}</span>
              <strong>{{ stats.deleted_facts ?? 0 }}</strong>
            </div>
            <div class="stat-line">
              <span>{{ tm('stats.profiles') }}</span>
              <strong>{{ stats.profiles ?? 0 }}</strong>
            </div>
            <div class="stat-line">
              <span>{{ tm('stats.queue') }}</span>
              <strong>
                {{ stats.worker?.queue_size ?? 0 }}/{{
                  stats.worker?.queue_max_size ?? 0
                }}
              </strong>
            </div>
            <v-chip
              class="mt-3"
              :color="stats.worker?.running ? 'success' : 'warning'"
              size="small"
            >
              {{
                stats.worker?.running
                  ? tm('stats.workerRunning')
                  : tm('stats.workerStopped')
              }}
            </v-chip>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="9">
        <v-card>
          <v-card-title class="d-flex flex-wrap ga-2 align-center">
            <span>{{ tm('memories.title') }}</span>
            <v-spacer />
            <v-btn
              color="primary"
              prepend-icon="mdi-refresh"
              variant="tonal"
              :loading="loading"
              @click="loadAll"
            >
              {{ tm('actions.refresh') }}
            </v-btn>
          </v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filters.person_id"
                  :label="tm('filters.personId')"
                  clearable
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="3">
                <v-text-field
                  v-model="filters.chat_id"
                  :label="tm('filters.chatId')"
                  clearable
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="2">
                <v-select
                  v-model="filters.status"
                  :items="statusOptions"
                  :aria-label="tm('filters.status')"
                  :placeholder="tm('filters.status')"
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="4">
                <v-text-field
                  v-model="filters.query"
                  :label="tm('filters.query')"
                  clearable
                  density="compact"
                  hide-details
                  prepend-inner-icon="mdi-magnify"
                  @keyup.enter="applyFilters"
                />
              </v-col>
            </v-row>
          </v-card-text>

          <v-table class="memory-table memory-table-desktop">
            <thead>
              <tr>
                <th>{{ tm('memories.id') }}</th>
                <th>{{ tm('memories.content') }}</th>
                <th>{{ tm('memories.person') }}</th>
                <th>{{ tm('memories.scope') }}</th>
                <th>{{ tm('memories.confidence') }}</th>
                <th>{{ tm('memories.status') }}</th>
                <th>{{ tm('memories.updatedAt') }}</th>
                <th class="text-right">{{ tm('actions.title') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="fact in facts" :key="fact.id">
                <td>{{ fact.id }}</td>
                <td class="fact-text">{{ fact.fact_text }}</td>
                <td>{{ fact.person_id }}</td>
                <td class="scope-text" :title="fact.scope_id">
                  {{ fact.scope_id }}
                </td>
                <td>{{ formatConfidence(fact.confidence) }}</td>
                <td>
                  <v-chip
                    size="small"
                    :color="fact.status === 'active' ? 'success' : 'grey'"
                  >
                    {{ statusLabel(fact.status) }}
                  </v-chip>
                </td>
                <td>{{ formatDate(fact.updated_at) }}</td>
                <td class="text-right">
                  <v-btn
                    icon="mdi-eye"
                    size="small"
                    variant="text"
                    :aria-label="tm('actions.view')"
                    @click="openDetail(fact)"
                  />
                  <v-btn
                    v-if="fact.status === 'active'"
                    icon="mdi-delete-outline"
                    size="small"
                    variant="text"
                    color="error"
                    :aria-label="tm('actions.delete')"
                    @click="confirmAction(fact, 'delete')"
                  />
                  <v-btn
                    v-else
                    icon="mdi-restore"
                    size="small"
                    variant="text"
                    color="primary"
                    :aria-label="tm('actions.restore')"
                    @click="confirmAction(fact, 'restore')"
                  />
                </td>
              </tr>
              <tr v-if="!loading && facts.length === 0">
                <td colspan="8" class="text-center text-medium-emphasis py-8">
                  {{ tm('messages.emptyFacts') }}
                </td>
              </tr>
            </tbody>
          </v-table>

          <div class="memory-cards-mobile">
            <v-card
              v-for="fact in facts"
              :key="fact.id"
              class="memory-fact-card"
              variant="tonal"
            >
              <div class="fact-card-head">
                <span class="text-caption text-medium-emphasis">
                  #{{ fact.id }} · {{ fact.person_id }}
                </span>
                <v-chip
                  size="small"
                  :color="fact.status === 'active' ? 'success' : 'grey'"
                >
                  {{ statusLabel(fact.status) }}
                </v-chip>
              </div>
              <p class="fact-card-text">{{ fact.fact_text }}</p>
              <div class="fact-card-meta">
                <span :title="fact.scope_id">{{ fact.scope_id }}</span>
                <span>{{ formatConfidence(fact.confidence) }}</span>
                <span>{{ formatDate(fact.updated_at) }}</span>
              </div>
              <div class="fact-card-actions">
                <v-btn
                  size="small"
                  variant="text"
                  prepend-icon="mdi-eye"
                  @click="openDetail(fact)"
                >
                  {{ tm('actions.view') }}
                </v-btn>
                <v-btn
                  v-if="fact.status === 'active'"
                  size="small"
                  variant="text"
                  color="error"
                  prepend-icon="mdi-delete-outline"
                  @click="confirmAction(fact, 'delete')"
                >
                  {{ tm('actions.delete') }}
                </v-btn>
                <v-btn
                  v-else
                  size="small"
                  variant="text"
                  color="primary"
                  prepend-icon="mdi-restore"
                  @click="confirmAction(fact, 'restore')"
                >
                  {{ tm('actions.restore') }}
                </v-btn>
              </div>
            </v-card>
            <div
              v-if="!loading && facts.length === 0"
              class="text-center text-medium-emphasis py-8"
            >
              {{ tm('messages.emptyFacts') }}
            </div>
          </div>

          <v-card-actions class="justify-end">
            <v-pagination
              v-model="page"
              :length="pageCount"
              density="comfortable"
              @update:model-value="loadFacts"
            />
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <v-row class="mt-2">
      <v-col cols="12" md="6">
        <v-card>
          <v-card-title>{{ tm('profiles.title') }}</v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="12" md="5">
                <v-text-field
                  v-model="profileFilters.person_id"
                  :label="tm('filters.personId')"
                  clearable
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="5">
                <v-text-field
                  v-model="profileFilters.chat_scope"
                  :label="tm('filters.scopeId')"
                  clearable
                  density="compact"
                  hide-details
                />
              </v-col>
              <v-col cols="12" md="2">
                <v-btn
                  block
                  color="primary"
                  variant="tonal"
                  @click="loadProfiles"
                >
                  {{ tm('actions.search') }}
                </v-btn>
              </v-col>
            </v-row>
          </v-card-text>
          <v-list lines="three">
            <v-list-item v-for="profile in profiles" :key="profile.id">
              <v-list-item-title class="text-truncate">
                {{ profile.person_id }} · {{ profile.chat_scope }}
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ profile.profile_text }}
              </v-list-item-subtitle>
              <template #append>
                <v-btn
                  icon="mdi-refresh"
                  size="small"
                  variant="text"
                  :aria-label="tm('profiles.refresh')"
                  @click="refreshProfile(profile)"
                />
              </template>
            </v-list-item>
            <v-list-item v-if="profiles.length === 0">
              <v-list-item-title class="text-medium-emphasis">
                {{ tm('messages.emptyProfiles') }}
              </v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card>
          <v-card-title>{{ tm('operations.title') }}</v-card-title>
          <v-list density="compact">
            <v-list-item v-for="operation in operations" :key="operation.id">
              <v-list-item-title class="text-truncate">
                {{ operation.action }} · {{ operation.target_type }} #{{
                  operation.target_id
                }}
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ operation.operator }} ·
                {{ formatDate(operation.created_at) }}
              </v-list-item-subtitle>
            </v-list-item>
            <v-list-item v-if="operations.length === 0">
              <v-list-item-title class="text-medium-emphasis">
                {{ tm('messages.emptyOperations') }}
              </v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="detailDialog" max-width="760">
      <v-card>
        <v-card-title>{{ tm('detail.title') }}</v-card-title>
        <v-card-text v-if="selectedDetail?.fact">
          <p class="text-body-1 mb-4">{{ selectedDetail.fact.fact_text }}</p>
          <v-row>
            <v-col cols="12" md="6">
              <strong>{{ tm('memories.person') }}:</strong>
              {{ selectedDetail.fact.person_id }}
            </v-col>
            <v-col cols="12" md="6">
              <strong>{{ tm('memories.chat') }}:</strong>
              {{ selectedDetail.fact.chat_id }}
            </v-col>
            <v-col cols="12" md="6">
              <strong>{{ tm('memories.scope') }}:</strong>
              {{ selectedDetail.fact.scope_id }}
            </v-col>
            <v-col cols="12" md="6">
              <strong>{{ tm('memories.status') }}:</strong>
              {{ statusLabel(selectedDetail.fact.status) }}
            </v-col>
          </v-row>
          <v-divider class="my-4" />
          <h3 class="text-subtitle-1 mb-2">{{ tm('operations.title') }}</h3>
          <v-list density="compact">
            <v-list-item
              v-for="operation in selectedDetail.operation_logs || []"
              :key="operation.operation_id"
            >
              <v-list-item-title>
                {{ operation.action }} · {{ operation.reason || '-' }}
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ operation.operator }} ·
                {{ formatDate(operation.created_at) }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="detailDialog = false">
            {{ tm('actions.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="actionDialog" max-width="520">
      <v-card>
        <v-card-title>
          {{
            pendingAction === 'delete'
              ? tm('confirm.deleteTitle')
              : tm('confirm.restoreTitle')
          }}
        </v-card-title>
        <v-card-text>
          <p class="mb-2">{{ pendingFact?.fact_text }}</p>
          <p class="text-caption text-medium-emphasis">
            {{ pendingFact?.person_id }} · {{ pendingFact?.scope_id }}
          </p>
          <v-text-field
            v-model="actionReason"
            :label="tm('confirm.reason')"
            class="mt-4"
            density="compact"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="actionDialog = false">
            {{ tm('actions.cancel') }}
          </v-btn>
          <v-btn
            :color="pendingAction === 'delete' ? 'error' : 'primary'"
            :loading="actionLoading"
            @click="runPendingAction"
          >
            {{
              pendingAction === 'delete'
                ? tm('actions.delete')
                : tm('actions.restore')
            }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import {
  memoryApi,
  type MemoryFactData,
  type MemoryFactDetailData,
  type MemoryOperationData,
  type MemoryProfileData,
  type MemoryStatsData,
} from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

const { tm } = useModuleI18n('features/alkaid/memory');

const facts = ref<MemoryFactData[]>([]);
const profiles = ref<MemoryProfileData[]>([]);
const operations = ref<MemoryOperationData[]>([]);
const stats = ref<MemoryStatsData>({});
const selectedDetail = ref<MemoryFactDetailData | null>(null);
const loading = ref(false);
const actionLoading = ref(false);
const detailDialog = ref(false);
const actionDialog = ref(false);
const pendingFact = ref<MemoryFactData | null>(null);
const pendingAction = ref<'delete' | 'restore'>('delete');
const actionReason = ref('');
const page = ref(1);
const pageSize = 10;
const total = ref(0);
const snackbar = ref({ show: false, text: '', color: 'success' });
type MemoryStatusFilter = 'active' | 'deleted' | 'all';

const filters = reactive<{
  person_id: string;
  chat_id: string;
  status: MemoryStatusFilter;
  query: string;
}>({
  person_id: '',
  chat_id: '',
  status: 'active',
  query: '',
});

const profileFilters = reactive({
  person_id: '',
  chat_scope: '',
});

const statusOptions = computed<
  Array<{ title: string; value: MemoryStatusFilter }>
>(() => [
  { title: tm('status.active'), value: 'active' },
  { title: tm('status.deleted'), value: 'deleted' },
  { title: tm('status.all'), value: 'all' },
]);

const pageCount = computed(() =>
  Math.max(Math.ceil(total.value / pageSize), 1),
);

function compactParams<T extends Record<string, string | number>>(params: T) {
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== ''),
  ) as Partial<T>;
}

function showMessage(text: string, color = 'success') {
  snackbar.value = { show: true, text, color };
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString() : '-';
}

function formatConfidence(value?: number) {
  return typeof value === 'number' ? value.toFixed(2) : '-';
}

function statusLabel(status?: string) {
  if (status === 'deleted') return tm('status.deleted');
  if (status === 'active') return tm('status.active');
  return status || '-';
}

async function loadStats() {
  const response = await memoryApi.stats();
  stats.value = response.data.data || {};
}

async function loadFacts() {
  loading.value = true;
  try {
    const response = await memoryApi.facts({
      page: page.value,
      page_size: pageSize,
      status: filters.status,
      ...compactParams({
        person_id: filters.person_id,
        chat_id: filters.chat_id,
        query: filters.query,
      }),
    });
    facts.value = response.data.data.items || [];
    total.value = response.data.data.total || 0;
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.loadFactsError'), 'error');
  } finally {
    loading.value = false;
  }
}

async function loadProfiles() {
  const response = await memoryApi.profiles({
    page: 1,
    page_size: 10,
    ...compactParams({
      person_id: profileFilters.person_id,
      chat_scope: profileFilters.chat_scope,
    }),
  });
  profiles.value = response.data.data.items || [];
}

async function loadOperations() {
  const response = await memoryApi.operations({ page: 1, page_size: 8 });
  operations.value = response.data.data.items || [];
}

async function loadAll() {
  await Promise.all([
    loadFacts(),
    loadProfiles(),
    loadOperations(),
    loadStats(),
  ]);
}

function applyFilters() {
  page.value = 1;
  void loadFacts();
}

async function openDetail(fact: MemoryFactData) {
  try {
    const response = await memoryApi.fact(fact.id);
    selectedDetail.value = response.data.data;
    detailDialog.value = true;
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.detailError'), 'error');
  }
}

function confirmAction(fact: MemoryFactData, action: 'delete' | 'restore') {
  pendingFact.value = fact;
  pendingAction.value = action;
  actionReason.value = '';
  actionDialog.value = true;
}

async function runPendingAction() {
  if (!pendingFact.value) return;
  actionLoading.value = true;
  try {
    const payload = actionReason.value
      ? { reason: actionReason.value }
      : undefined;
    if (pendingAction.value === 'delete') {
      await memoryApi.deleteFact(pendingFact.value.id, payload);
      showMessage(tm('messages.deleteSuccess'));
    } else {
      await memoryApi.restoreFact(pendingFact.value.id, payload);
      showMessage(tm('messages.restoreSuccess'));
    }
    actionDialog.value = false;
    await loadAll();
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.actionError'), 'error');
  } finally {
    actionLoading.value = false;
  }
}

async function refreshProfile(profile: MemoryProfileData) {
  try {
    await memoryApi.refreshProfile(profile.person_id, {
      chat_scope: profile.chat_scope,
    });
    showMessage(tm('messages.refreshQueued'));
    await loadStats();
  } catch (error) {
    console.error(error);
    showMessage(tm('messages.refreshError'), 'error');
  }
}

onMounted(() => {
  void loadAll();
});
</script>

<style scoped>
.memory-page {
  min-height: 100%;
}

.stat-line {
  align-items: center;
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
}

.memory-table {
  table-layout: fixed;
}

.memory-table th:nth-child(1),
.memory-table td:nth-child(1) {
  width: 48px;
}

.memory-table th:nth-child(5),
.memory-table td:nth-child(5) {
  width: 64px;
}

.memory-table th:nth-child(6),
.memory-table td:nth-child(6) {
  width: 76px;
}

.memory-table th:nth-child(7),
.memory-table td:nth-child(7) {
  width: 112px;
}

.memory-table th:nth-child(8),
.memory-table td:nth-child(8) {
  width: 88px;
}

.fact-text {
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.scope-text {
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 0.875rem;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.memory-cards-mobile {
  display: none;
}

.memory-fact-card {
  margin-top: 12px;
  padding: 14px;
}

.fact-card-head,
.fact-card-actions,
.fact-card-meta {
  align-items: center;
  display: flex;
}

.fact-card-head {
  justify-content: space-between;
}

.fact-card-text {
  font-size: 1rem;
  line-height: 1.65;
  margin: 12px 0;
  white-space: normal;
}

.fact-card-meta {
  color: rgba(var(--v-theme-on-surface), 0.62);
  flex-wrap: wrap;
  font-size: 0.78rem;
  gap: 6px 12px;
}

.fact-card-meta span:first-child {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fact-card-actions {
  gap: 4px;
  justify-content: flex-end;
  margin-top: 8px;
}

@media (max-width: 700px) {
  .memory-table-desktop {
    display: none;
  }

  .memory-cards-mobile {
    display: block;
  }
}
</style>

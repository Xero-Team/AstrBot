<!--
  Everything the BTW dual-loop feature configures, in one place.

  These settings used to sit inside the AI section of the config file page,
  where the work loop's own boundary was easy to miss among the model and
  agent-runner options.  The work loop is a separate execution path with its
  own runtime, its own read-only boundary, and its own coding agents, so it
  gets a page of its own under More Features.
-->
<template>
  <div class="dashboard-page btw-page">
    <v-container fluid class="dashboard-shell pa-4 pa-md-6">
      <div class="dashboard-header">
        <div class="dashboard-header-main">
          <h1 class="dashboard-title">
            {{ tm('btwPage.title') }}
            <ConfigDocsLink docs="dev/astrbot-config.html" />
          </h1>
          <p class="dashboard-subtitle">{{ tm('btwPage.subtitle') }}</p>
        </div>
        <div class="dashboard-header-actions">
          <v-btn
            class="btw-page__save"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-content-save"
            :loading="saving"
            :disabled="!loaded || saving || !hasUnsavedChanges"
            @click="save()"
          >
            {{ saving ? tm('btwPage.saving') : tm('btwPage.save') }}
          </v-btn>
        </div>
      </div>

      <v-alert
        v-if="loadFailed"
        class="mb-4"
        density="compact"
        variant="tonal"
        type="error"
      >
        {{ tm('btwPage.loadError') }}
        <template #append>
          <v-btn size="small" variant="text" @click="loadAll">
            {{ tm('btwPage.retry') }}
          </v-btn>
        </template>
      </v-alert>

      <v-skeleton-loader v-else-if="!loaded" type="article" />

      <template v-else>
        <div
          v-if="hasUnsavedChanges"
          class="btw-page__unsaved"
          role="status"
          aria-live="polite"
        >
          <v-icon size="18" color="warning">mdi-alert-circle-outline</v-icon>
          <span class="btw-page__unsaved-text">
            {{ tm('btwPage.unsavedNotice') }}
          </span>
          <v-btn
            variant="text"
            size="small"
            :disabled="saving"
            @click="discardChanges"
          >
            {{ tm('btwPage.discard') }}
          </v-btn>
        </div>

        <v-card class="btw-page__scope" rounded="md" variant="outlined">
          <v-select
            :model-value="scope"
            class="btw-page__scope-select"
            :items="scopeOptions"
            :label="tm('btwPage.appliesTo')"
            :hint="tm('btwPage.appliesToHint')"
            persistent-hint
            density="compact"
            variant="outlined"
            @update:model-value="onScopeChange"
          />
        </v-card>

        <AstrBotCoreConfigWrapper
          v-if="hasBtwSections"
          :key="configKey"
          :metadata="btwSections"
          :config-data="configData"
        />
        <v-alert v-else density="compact" variant="tonal" type="warning">
          {{ tm('btwPage.metadataMissing') }}
        </v-alert>
      </template>
    </v-container>

    <v-snackbar v-model="snackbar" :color="snackColor" :timeout="3000">
      {{ snackMessage }}
    </v-snackbar>

    <DashboardStepUpDialog
      v-model="stepUpOpen"
      :loading="stepUpLoading"
      :error-message="stepUpError"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />

    <DashboardTwoFactorDialog
      v-model="twoFactorOpen"
      :error-message="twoFactorError"
      :saving="saving"
      @confirm="confirmTwoFactor"
      @cancel="twoFactorOpen = false"
    />

    <UnsavedChangesConfirmDialog ref="unsavedChangesDialog" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { configProfileApi, type OpenConfig } from '@/api/v1';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import ConfigDocsLink from '@/components/shared/ConfigDocsLink.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import DashboardTwoFactorDialog from '@/components/shared/DashboardTwoFactorDialog.vue';
import UnsavedChangesConfirmDialog from '@/components/config/UnsavedChangesConfirmDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useModuleI18n } from '@/i18n/composables';
import { runConfigMutationWithStepUp, stepUpHeaders } from '@/utils/stepUp';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';

defineOptions({ name: 'BtwPage' });

/** The id the backend uses for the profile that is the running configuration. */
const SYSTEM_SCOPE = 'default';

interface UnsavedChangesDialogExposed {
  open: (options: {
    title: string;
    message: string;
    confirmHint: string;
    cancelHint: string;
    closeHint: string;
  }) => Promise<boolean | 'close'>;
}

const { tm } = useModuleI18n('features/config');
const { tm: tmMetadata } = useModuleI18n('features/config-metadata');
const confirmDialog = useConfirmDialog();
const unsavedChangesDialog = ref<UnsavedChangesDialogExposed | null>(null);

const {
  dialogOpen: stepUpOpen,
  loading: stepUpLoading,
  errorMessage: stepUpError,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const scope = ref<string>(SYSTEM_SCOPE);
const scopeOptions = ref<{ title: string; value: string }[]>([
  { title: tm('configSelection.defaultConfig'), value: SYSTEM_SCOPE },
]);

const configData = ref<OpenConfig>({});
const metadata = ref<OpenConfig>({});
const loaded = ref(false);
const loadFailed = ref(false);
/** Remounts the editor after a reload so it re-reads the new value. */
const configKey = ref(0);
const savedSnapshot = ref('');

const saving = ref(false);
const twoFactorOpen = ref(false);
const twoFactorError = ref('');
const snackbar = ref(false);
const snackMessage = ref('');
const snackColor = ref<'success' | 'error'>('success');

const btwMetadata = computed(
  () => asRecord(asRecord(metadata.value?.ai_group)?.metadata)?.btw,
);

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

interface BtwCategory {
  key: string;
  icon: string;
  labelKey: string;
  hintKey: string;
  matches: (selector: string) => boolean;
}

/**
 * The page reads one flat `btw` group; these categories fold it into the same
 * section/card layout the config page uses. Item selectors stay authoritative,
 * so a new `btw.*` key still renders under the fallback category.
 */
const BTW_CATEGORIES: BtwCategory[] = [
  {
    key: 'general',
    icon: 'mdi-tune-variant',
    labelKey: 'btw_page.general',
    hintKey: 'btw_page.generalHint',
    matches: (selector) => selector === 'btw.enabled',
  },
  {
    key: 'conversation_loop',
    icon: 'mdi-message-text-outline',
    labelKey: 'btw_page.conversationLoop',
    hintKey: 'btw_page.conversationLoopHint',
    matches: (selector) => selector.startsWith('btw.conversation_loop.'),
  },
  {
    key: 'work_loop',
    icon: 'mdi-briefcase-outline',
    labelKey: 'btw_page.workLoop',
    hintKey: 'btw_page.workLoopHint',
    matches: (selector) =>
      selector.startsWith('btw.work_loop.') ||
      selector.startsWith('btw.work_session.'),
  },
  {
    key: 'classifier',
    icon: 'mdi-call-split',
    labelKey: 'btw_page.classifier',
    hintKey: 'btw_page.classifierHint',
    matches: (selector) => selector.startsWith('btw.classifier.'),
  },
  {
    key: 'routes',
    icon: 'mdi-source-branch',
    labelKey: 'btw_page.routes',
    hintKey: 'btw_page.routesHint',
    matches: (selector) => selector.endsWith('_routes'),
  },
  {
    key: 'other',
    icon: 'mdi-dots-horizontal',
    labelKey: 'btw_page.other',
    hintKey: 'btw_page.otherHint',
    matches: () => true,
  },
];

const btwSections = computed<Record<string, Record<string, unknown>>>(() => {
  const items = asRecord(asRecord(btwMetadata.value)?.items);
  if (!items) return {};

  const buckets = new Map<string, Record<string, unknown>>(
    BTW_CATEGORIES.map((category) => [category.key, {}]),
  );
  for (const [selector, itemMeta] of Object.entries(items)) {
    const category = BTW_CATEGORIES.find((entry) => entry.matches(selector));
    buckets.get(category?.key ?? 'other')![selector] = itemMeta;
  }

  const sections: Record<string, Record<string, unknown>> = {};
  for (const category of BTW_CATEGORIES) {
    const categoryItems = buckets.get(category.key)!;
    if (Object.keys(categoryItems).length === 0) continue;
    sections[category.key] = {
      label: tmMetadata(category.labelKey),
      icon: category.icon,
      metadata: {
        [category.key]: {
          type: 'object',
          description: category.hintKey,
          items: categoryItems,
        },
      },
    };
  }
  return sections;
});

const hasBtwSections = computed(
  () => Object.keys(btwSections.value).length > 0,
);

function showSnack(message: string, color: 'success' | 'error') {
  snackMessage.value = message;
  snackColor.value = color;
  snackbar.value = true;
}

function snapshot(value: OpenConfig) {
  return JSON.stringify(value ?? {});
}

async function loadProfiles() {
  try {
    const response = await configProfileApi.list();
    const payload = asRecord(response.data?.data);
    const items = Array.isArray(payload?.info_list) ? payload.info_list : [];
    const named = items
      .map((item) => asRecord(item))
      .filter((item): item is Record<string, unknown> => item !== null)
      .map((item) => ({
        id: String(item.id ?? ''),
        name: String(item.name ?? item.id ?? ''),
      }))
      .filter((item) => item.id && item.id !== SYSTEM_SCOPE);
    scopeOptions.value = [
      { title: tm('configSelection.defaultConfig'), value: SYSTEM_SCOPE },
      ...named.map((item) => ({ title: item.name, value: item.id })),
    ];
  } catch {
    // The list is a convenience: the default profile is always editable.
  }
}

async function loadConfig() {
  loadFailed.value = false;
  try {
    // The profile endpoint, even for the default scope: it is the one that
    // serves the whole metadata tree, and the BTW group lives in the AI
    // section of it.  The system-config endpoint returns the system group
    // alone, so reading through it would find nothing to render.
    const response = await configProfileApi.get(scope.value);
    const payload = asRecord(response.data?.data);
    configData.value = asRecord(payload?.config) ?? {};
    metadata.value = asRecord(payload?.metadata) ?? {};
    savedSnapshot.value = snapshot(configData.value);
    configKey.value += 1;
    loaded.value = true;
  } catch {
    loaded.value = false;
    loadFailed.value = true;
  }
}

async function loadAll() {
  await loadProfiles();
  await loadConfig();
}

const hasUnsavedChanges = computed(
  () => loaded.value && snapshot(configData.value) !== savedSnapshot.value,
);

/** Restore the last saved profile, dropping edits made since. */
function discardChanges() {
  if (!hasUnsavedChanges.value) return;
  configData.value = JSON.parse(savedSnapshot.value) as OpenConfig;
  configKey.value += 1;
}

async function save(twoFactorCode = '') {
  if (saving.value) return;
  await saveProfile(scope.value, twoFactorCode);
}

/**
 * Save the settings currently in hand into ``target``.
 *
 * Separate from ``save`` because switching profiles has to write the profile
 * the operator is leaving, which is no longer the one the select shows.
 *
 * Returns:
 *   Whether the profile now holds what the page was showing.
 */
async function saveProfile(target: string, twoFactorCode = '') {
  if (saving.value) return false;
  saving.value = true;
  const submittedSnapshot = snapshot(configData.value);
  const submittedConfig = JSON.parse(submittedSnapshot) as OpenConfig;
  const headers: Record<string, string> = {};
  if (twoFactorCode) headers['X-2FA-Code'] = twoFactorCode;

  try {
    const response = await runConfigMutationWithStepUp(
      (stepUp) => {
        if (stepUp) Object.assign(headers, stepUpHeaders(stepUp));
        const requestConfig = {
          headers,
          validateStatus: (status: number) =>
            (status >= 200 && status < 300) || status === 401,
        };
        return configProfileApi.update(target, submittedConfig, requestConfig);
      },
      target,
      requestStepUp,
    );
    if (!response) {
      saving.value = false;
      return false;
    }

    const payload = asRecord(response.data?.data);
    if (response.status === 401 && payload?.totp_required === true) {
      twoFactorError.value = twoFactorCode
        ? tm('btwPage.twoFactorRejected')
        : '';
      twoFactorOpen.value = true;
      saving.value = false;
      return false;
    }

    if (response.data?.status === 'ok') {
      twoFactorOpen.value = false;
      twoFactorError.value = '';
      savedSnapshot.value = submittedSnapshot;
      showSnack(response.data?.message || tm('btwPage.saveSuccess'), 'success');
      return true;
    }
    showSnack(response.data?.message || tm('btwPage.saveError'), 'error');
    return false;
  } catch {
    showSnack(tm('btwPage.saveError'), 'error');
    return false;
  } finally {
    saving.value = false;
  }
}

function confirmTwoFactor(code: string) {
  twoFactorError.value = '';
  void save(code);
}

function createUnsavedChangesDialogOptions(message: string) {
  return {
    title: tm('unsavedChangesWarning.dialogTitle'),
    message,
    confirmHint: `${tm('unsavedChangesWarning.options.saveAndSwitch')}:${tm('unsavedChangesWarning.options.confirm')}`,
    cancelHint: `${tm('unsavedChangesWarning.options.discardAndSwitch')}:${tm('unsavedChangesWarning.options.cancel')}`,
    closeHint: `${tm('unsavedChangesWarning.options.closeCard')}:"x"`,
  };
}

async function openUnsavedChangesDialog(message: string) {
  return (
    (await unsavedChangesDialog.value?.open(
      createUnsavedChangesDialogOptions(message),
    )) ?? false
  );
}

/**
 * Point the page at another profile, without losing edits made in this one.
 *
 * The select is bound one way on purpose: it stays on the profile being
 * edited until this decides to move, so declining the prompt needs no undo.
 */
async function onScopeChange(next: unknown) {
  const target = typeof next === 'string' ? next : '';
  if (!target || target === scope.value) return;

  if (!hasUnsavedChanges.value) {
    scope.value = target;
    await loadConfig();
    return;
  }

  const previous = scope.value;
  const saveAndSwitch = await openUnsavedChangesDialog(
    tm('unsavedChangesWarning.switchConfig'),
  );
  if (saveAndSwitch === 'close') return;
  if (saveAndSwitch && !(await saveProfile(previous))) return;

  scope.value = target;
  await loadConfig();
}

onBeforeRouteLeave(async () => {
  if (!hasUnsavedChanges.value) return true;
  // Staying is the safe answer: what is unsaved is the work loop's boundary.
  return askForConfirmation(
    `${tm('btwPage.unsavedTitle')}\n\n${tm('btwPage.unsavedMessage')}`,
    confirmDialog,
  );
});

onMounted(loadAll);
</script>

<style scoped>
@import '@/styles/dashboard-shell.css';

.btw-page__unsaved {
  display: flex;
  align-items: center;
  gap: var(--astrbot-space-2);
  padding: var(--astrbot-space-3);
  margin-bottom: var(--astrbot-space-4);
  border: 1px solid rgb(var(--v-theme-warning));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant));
  color: var(--dashboard-text);
  font-size: 13px;
  line-height: 18px;
}

.btw-page__unsaved-text {
  flex: 1;
}

.btw-page__scope {
  max-width: 420px;
  padding: var(--astrbot-space-4);
  margin-bottom: var(--astrbot-space-4);
}
</style>

<!--
  The provider list each coding CLI's own configuration is switched between.

  The agents a task is delegated to are configured on the BTW page; which
  provider they run against is decided here, because a switch rewrites the
  CLI's own global configuration and a run inherits it.  Keeping the list next
  to the switch is what makes "switch this CLI" and "what this CLI is
  configured with" the same subject.

  The list is AstrBot configuration and is saved with the profile; only the
  switch touches a file AstrBot does not own, so it asks for a step-up.
-->
<template>
  <div class="third-party-agents-page">
    <header class="third-party-agents-page__header">
      <div>
        <h1 class="third-party-agents-page__title">
          {{ tm('thirdPartyAgentsPage.title') }}
        </h1>
        <p class="third-party-agents-page__subtitle">
          {{ tm('thirdPartyAgentsPage.subtitle') }}
        </p>
      </div>
      <ConfigDocsLink docs="dev/astrbot-config.html" />
    </header>

    <v-alert
      v-if="loadFailed"
      class="mb-4"
      density="compact"
      variant="tonal"
      type="error"
    >
      {{ tm('thirdPartyAgentsPage.loadError') }}
      <template #append>
        <v-btn size="small" variant="text" @click="load">
          {{ tm('thirdPartyAgentsPage.retry') }}
        </v-btn>
      </template>
    </v-alert>

    <v-skeleton-loader v-else-if="!loaded" type="article" />

    <CodingCliProviders v-else v-model="providers" />

    <FloatingActionStack :label="tm('thirdPartyAgentsPage.actions')">
      <v-btn
        class="third-party-agents-page__save"
        color="primary"
        :loading="saving"
        :disabled="!loaded || !hasUnsavedChanges"
        @click="save()"
      >
        {{ tm('thirdPartyAgentsPage.save') }}
      </v-btn>
    </FloatingActionStack>

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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import {
  configProfileApi,
  type OpenConfig,
  type StoredCliProvider,
} from '@/api/v1';
import CodingCliProviders from '@/components/shared/CodingCliProviders.vue';
import ConfigDocsLink from '@/components/shared/ConfigDocsLink.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import DashboardTwoFactorDialog from '@/components/shared/DashboardTwoFactorDialog.vue';
import FloatingActionStack from '@/components/ui/FloatingActionStack.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useModuleI18n } from '@/i18n/composables';
import { runConfigMutationWithStepUp, stepUpHeaders } from '@/utils/stepUp';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';

defineOptions({ name: 'ThirdPartyAgentsPage' });

/** The id the backend uses for the profile that is the running configuration. */
const SYSTEM_SCOPE = 'default';

const { tm } = useModuleI18n('features/config');
const confirmDialog = useConfirmDialog();

const {
  dialogOpen: stepUpOpen,
  loading: stepUpLoading,
  errorMessage: stepUpError,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const configData = ref<OpenConfig>({});
const loaded = ref(false);
const loadFailed = ref(false);
const savedSnapshot = ref('');

const saving = ref(false);
const twoFactorOpen = ref(false);
const twoFactorError = ref('');
const snackbar = ref(false);
const snackMessage = ref('');
const snackColor = ref<'success' | 'error'>('success');

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

/** What a config response writes where a stored secret would be. */
const REDACTED_SECRET_PLACEHOLDER = '__ASTRBOT_REDACTED__';

/**
 * The operator's own key, never the marker a response puts in its place.
 *
 * Treating the marker as a key is how it ends up stored as one: it is what the
 * field would show, and what the next save would write back.
 */
function typedKey(value: unknown): string {
  const key = text(value);
  return key === REDACTED_SECRET_PLACEHOLDER ? '' : key;
}

function showSnack(message: string, color: 'success' | 'error') {
  snackMessage.value = message;
  snackColor.value = color;
  snackbar.value = true;
}

function snapshot(value: OpenConfig) {
  return JSON.stringify(value ?? {});
}

/** The raw stored list, so an entry keeps any field this page does not edit. */
function rawProviders(config: OpenConfig): Record<string, unknown>[] {
  const btw = asRecord((config as Record<string, unknown>)?.btw) ?? {};
  return (Array.isArray(btw.cli_providers) ? btw.cli_providers : []).filter(
    (entry): entry is Record<string, unknown> => asRecord(entry) !== null,
  );
}

/**
 * The provider list as one value, read from and written back into the profile.
 *
 * A binding rather than a copy: what the editor changes is part of the
 * configuration this page saves, so the unsaved-changes check below covers the
 * list.  A stored key is carried through untouched -- an empty field means
 * "leave it alone", never "erase it", because the editor cannot tell the two
 * apart -- and what carries it is the marker, put back only where it came from.
 */
const providers = computed<StoredCliProvider[]>({
  get: () =>
    rawProviders(configData.value).map((entry) => ({
      id: text(entry.id).trim(),
      name: text(entry.name).trim() || text(entry.id).trim(),
      base_url: text(entry.base_url).trim(),
      model: text(entry.model).trim(),
      note: text(entry.note).trim(),
      has_api_key: Boolean(text(entry.api_key).trim()),
      current: false,
      cli: text(entry.cli).trim(),
      api_key: typedKey(entry.api_key),
    })),
  set: (next) => {
    const config = configData.value as Record<string, unknown>;
    const btw = asRecord(config.btw) ?? {};
    const byId = new Map(
      rawProviders(configData.value).map((entry) => [
        text(entry.id).trim(),
        entry,
      ]),
    );
    btw.cli_providers = next.map((provider) => {
      const entry: Record<string, unknown> = {
        ...(byId.get(provider.id) ?? {}),
        id: provider.id,
        name: provider.name,
        base_url: provider.base_url,
        model: provider.model,
        note: provider.note,
      };
      if (provider.cli) entry.cli = provider.cli;
      else delete entry.cli;
      if (provider.api_key) {
        entry.api_key = provider.api_key;
      } else if (provider.has_api_key) {
        // The profile still holds a key for this entry and the operator did not
        // type a new one, so the marker is what says "keep it".  It is posted
        // only where it came from: the profile resolves it by the entry's id,
        // and a copy of this entry has an id the profile has never seen.
        entry.api_key = REDACTED_SECRET_PLACEHOLDER;
      } else {
        delete entry.api_key;
      }
      return entry;
    });
    config.btw = btw;
  },
});

async function load() {
  loadFailed.value = false;
  try {
    // The running profile: a switch resolves the provider in that one's list,
    // so it is the list this page has to show.
    const response = await configProfileApi.get(SYSTEM_SCOPE);
    const payload = asRecord(response.data?.data);
    configData.value = asRecord(payload?.config) ?? {};
    savedSnapshot.value = snapshot(configData.value);
    loaded.value = true;
  } catch {
    loaded.value = false;
    loadFailed.value = true;
  }
}

const hasUnsavedChanges = computed(
  () => loaded.value && snapshot(configData.value) !== savedSnapshot.value,
);

async function save(twoFactorCode = '') {
  if (saving.value) return;
  saving.value = true;
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
        return configProfileApi.update(
          SYSTEM_SCOPE,
          configData.value,
          requestConfig,
        );
      },
      SYSTEM_SCOPE,
      requestStepUp,
    );
    if (!response) {
      saving.value = false;
      return;
    }

    const payload = asRecord(response.data?.data);
    if (response.status === 401 && payload?.totp_required === true) {
      twoFactorError.value = twoFactorCode
        ? tm('thirdPartyAgentsPage.twoFactorRejected')
        : '';
      twoFactorOpen.value = true;
      saving.value = false;
      return;
    }

    if (response.data?.status === 'ok') {
      twoFactorOpen.value = false;
      twoFactorError.value = '';
      savedSnapshot.value = snapshot(configData.value);
      showSnack(
        response.data?.message || tm('thirdPartyAgentsPage.saveSuccess'),
        'success',
      );
    } else {
      showSnack(
        response.data?.message || tm('thirdPartyAgentsPage.saveError'),
        'error',
      );
    }
  } catch {
    showSnack(tm('thirdPartyAgentsPage.saveError'), 'error');
  } finally {
    saving.value = false;
  }
}

function confirmTwoFactor(code: string) {
  twoFactorError.value = '';
  void save(code);
}

onBeforeRouteLeave(async () => {
  if (!hasUnsavedChanges.value) return true;
  // Staying is the safe answer: what is unsaved is this host's coding CLIs.
  return askForConfirmation(
    `${tm('thirdPartyAgentsPage.unsavedTitle')}\n\n${tm('thirdPartyAgentsPage.unsavedMessage')}`,
    confirmDialog,
  );
});

onMounted(load);
</script>

<style scoped>
.third-party-agents-page {
  padding: 16px;
}

.third-party-agents-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.third-party-agents-page__title {
  font-size: 1.25rem;
  font-weight: 600;
}

.third-party-agents-page__subtitle {
  margin-top: 4px;
  opacity: 0.7;
  max-width: 70ch;
}
</style>

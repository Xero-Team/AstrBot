<!--
  Provider switching for the coding CLIs, in the shape cc-switch uses.

  Each CLI gets its own list of providers, and the operator clicks 启用 on a
  card to make that one current: it is written into the CLI's own configuration
  file, which is what the CLI uses everywhere, including the sessions started by
  hand.  A delegated run is unaffected -- it layers its own config over these
  files rather than reading them, so switching here never changes a run.

  The list itself is AstrBot configuration, saved with the profile like any
  other setting.  Only the switch touches a file AstrBot does not own, so it
  asks for confirmation and a step-up credential.
-->
<template>
  <div class="cli-config-page">
    <header class="cli-config-page__header">
      <div>
        <h1 class="cli-config-page__title">{{ tm('cliConfigPage.title') }}</h1>
        <p class="cli-config-page__subtitle">
          {{ tm('cliConfigPage.subtitle') }}
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
      {{ tm('cliConfigPage.loadError') }}
      <template #append>
        <v-btn size="small" variant="text" @click="load">
          {{ tm('cliConfigPage.retry') }}
        </v-btn>
      </template>
    </v-alert>

    <v-skeleton-loader v-else-if="!loaded" type="article" />

    <template v-else>
      <v-alert class="mb-4" density="compact" variant="tonal" type="info">
        {{ tm('cliConfigPage.untouchedHint') }}
      </v-alert>

      <v-card
        v-for="state in clis"
        :key="state.cli"
        class="cli-config-page__cli mb-6"
        variant="outlined"
      >
        <v-card-title class="d-flex align-center flex-wrap ga-2">
          <span class="text-body-1">{{ cliLabel(state.cli) }}</span>
          <v-chip
            v-if="state.managed"
            class="cli-config-page__managed"
            color="primary"
            size="small"
            variant="tonal"
            prepend-icon="mdi-check-circle-outline"
          >
            {{ tm('cliConfigPage.managed') }}
          </v-chip>
          <v-chip
            v-if="state.has_credential"
            class="cli-config-page__credential"
            color="warning"
            size="small"
            variant="tonal"
            prepend-icon="mdi-key-outline"
          >
            {{ tm('cliConfigPage.credentialStored') }}
          </v-chip>
          <v-spacer />
          <v-btn
            class="cli-config-page__add"
            color="primary"
            variant="tonal"
            size="small"
            prepend-icon="mdi-plus"
            @click="openForm(state.cli)"
          >
            {{ tm('cliConfigPage.addProvider') }}
          </v-btn>
        </v-card-title>

        <v-card-text>
          <div class="cli-config-page__path">
            <code>{{ state.path }}</code>
          </div>
          <div class="text-body-2 text-medium-emphasis mb-3">
            {{
              state.exists
                ? tm('cliConfigPage.fileExists')
                : tm('cliConfigPage.fileAbsent')
            }}
          </div>

          <v-alert
            v-if="!providersFor(state.cli).length"
            class="cli-config-page__empty"
            density="compact"
            variant="tonal"
            type="info"
          >
            {{ tm('cliConfigPage.noProviders') }}
          </v-alert>

          <v-row v-else density="compact">
            <v-col
              v-for="provider in providersFor(state.cli)"
              :key="provider.id"
              cols="12"
              md="6"
            >
              <v-card
                class="cli-config-page__provider h-100"
                variant="tonal"
                :class="{
                  'cli-config-page__provider--current': isCurrent(
                    state,
                    provider,
                  ),
                }"
              >
                <v-card-text>
                  <div class="d-flex align-center ga-2 mb-1">
                    <span class="text-subtitle-1">{{ provider.name }}</span>
                    <v-chip
                      v-if="isCurrent(state, provider)"
                      class="cli-config-page__current"
                      color="primary"
                      size="small"
                      variant="flat"
                      prepend-icon="mdi-check"
                    >
                      {{ tm('cliConfigPage.current') }}
                    </v-chip>
                  </div>

                  <div class="cli-config-page__endpoint text-body-2">
                    {{ provider.base_url || tm('cliConfigPage.noBaseUrl') }}
                  </div>
                  <div
                    v-if="provider.model"
                    class="text-body-2 text-medium-emphasis"
                  >
                    {{ provider.model }}
                  </div>
                  <div
                    v-if="provider.note"
                    class="cli-config-page__note text-body-2 text-medium-emphasis"
                  >
                    {{ provider.note }}
                  </div>
                  <div class="text-body-2 text-medium-emphasis mt-1">
                    {{
                      provider.has_api_key
                        ? tm('cliConfigPage.keyPresent')
                        : tm('cliConfigPage.keyAbsent')
                    }}
                  </div>

                  <div class="d-flex align-center flex-wrap ga-1 mt-3">
                    <v-btn
                      class="cli-config-page__switch"
                      color="primary"
                      variant="flat"
                      size="small"
                      prepend-icon="mdi-swap-horizontal"
                      :aria-label="`${tm('cliConfigPage.enable')}: ${provider.name}`"
                      :disabled="isCurrent(state, provider)"
                      :loading="busy === switchKey(state.cli, provider.id)"
                      @click="switchTo(state, provider)"
                    >
                      {{ tm('cliConfigPage.enable') }}
                    </v-btn>
                    <v-btn
                      class="cli-config-page__edit"
                      variant="text"
                      size="small"
                      prepend-icon="mdi-pencil"
                      :aria-label="`${tm('cliConfigPage.edit')}: ${provider.name}`"
                      @click="openForm(state.cli, provider)"
                    >
                      {{ tm('cliConfigPage.edit') }}
                    </v-btn>
                    <v-btn
                      class="cli-config-page__duplicate"
                      variant="text"
                      size="small"
                      prepend-icon="mdi-content-copy"
                      :aria-label="`${tm('cliConfigPage.duplicate')}: ${provider.name}`"
                      @click="duplicate(state.cli, provider)"
                    >
                      {{ tm('cliConfigPage.duplicate') }}
                    </v-btn>
                    <v-btn
                      class="cli-config-page__delete"
                      color="error"
                      variant="text"
                      size="small"
                      prepend-icon="mdi-delete-outline"
                      :aria-label="`${tm('cliConfigPage.delete')}: ${provider.name}`"
                      @click="remove(provider)"
                    >
                      {{ tm('cliConfigPage.delete') }}
                    </v-btn>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <div class="d-flex justify-end mt-2">
            <v-btn
              class="cli-config-page__restore"
              color="error"
              variant="text"
              size="small"
              prepend-icon="mdi-backup-restore"
              :disabled="!state.managed"
              :loading="busy === `restore:${state.cli}`"
              @click="restore(state)"
            >
              {{ tm('cliConfigPage.restore') }}
            </v-btn>
          </div>
        </v-card-text>
      </v-card>
    </template>

    <!--
      The overlays sit behind their own element so the page has a single root to
      receive the class an injected mount passes down; a fragment would make Vue
      warn about extraneous attributes instead.
    -->
    <div class="cli-config-page__overlays">
      <FloatingActionStack :label="tm('cliConfigPage.actions')">
        <v-btn
          class="cli-config-page__save"
          color="primary"
          :loading="saving"
          :disabled="!dirty"
          @click="save"
        >
          {{ tm('cliConfigPage.save') }}
        </v-btn>
      </FloatingActionStack>

      <v-dialog v-model="formOpen" max-width="640">
        <v-card>
          <v-card-title>
            {{
              formEditing
                ? tm('cliConfigPage.editProvider')
                : tm('cliConfigPage.addProvider')
            }}
          </v-card-title>
          <v-card-text>
            <v-row density="compact">
              <v-col cols="12" sm="6">
                <v-text-field
                  class="cli-config-page__form-id"
                  :model-value="form.id"
                  :label="tm('cliConfigPage.providerId')"
                  :hint="tm('cliConfigPage.providerIdHint')"
                  persistent-hint
                  density="compact"
                  variant="outlined"
                  @update:model-value="form.id = text($event)"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  class="cli-config-page__form-name"
                  :model-value="form.name"
                  :label="tm('cliConfigPage.providerName')"
                  :placeholder="form.id"
                  density="compact"
                  variant="outlined"
                  hide-details
                  @update:model-value="form.name = text($event)"
                />
              </v-col>
              <v-col cols="12">
                <v-text-field
                  class="cli-config-page__form-base-url"
                  :model-value="form.base_url"
                  :label="tm('cliConfigPage.baseUrl')"
                  :hint="
                    form.cli === 'codex'
                      ? tm('cliConfigPage.baseUrlHintCodex')
                      : tm('cliConfigPage.baseUrlHintClaude')
                  "
                  persistent-hint
                  density="compact"
                  variant="outlined"
                  @update:model-value="form.base_url = text($event)"
                />
              </v-col>
              <v-col cols="12">
                <v-text-field
                  class="cli-config-page__form-api-key"
                  :model-value="form.api_key"
                  :type="showKey ? 'text' : 'password'"
                  :label="tm('cliConfigPage.apiKey')"
                  :hint="tm('cliConfigPage.apiKeyHint')"
                  persistent-hint
                  density="compact"
                  variant="outlined"
                  :append-inner-icon="
                    showKey ? 'mdi-eye-off-outline' : 'mdi-eye-outline'
                  "
                  @click:append-inner="showKey = !showKey"
                  @update:model-value="form.api_key = text($event)"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  class="cli-config-page__form-model"
                  :model-value="form.model"
                  :label="tm('cliConfigPage.model')"
                  :hint="tm('cliConfigPage.modelHint')"
                  persistent-hint
                  density="compact"
                  variant="outlined"
                  @update:model-value="form.model = text($event)"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  class="cli-config-page__form-note"
                  :model-value="form.note"
                  :label="tm('cliConfigPage.note')"
                  density="compact"
                  variant="outlined"
                  hide-details
                  @update:model-value="form.note = text($event)"
                />
              </v-col>
            </v-row>
            <v-alert
              v-if="formError"
              class="cli-config-page__form-error mt-3"
              density="compact"
              variant="tonal"
              type="warning"
            >
              {{ formError }}
            </v-alert>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="formOpen = false">
              {{ tm('cliConfigPage.cancel') }}
            </v-btn>
            <v-btn
              class="cli-config-page__form-confirm"
              color="primary"
              variant="tonal"
              @click="confirmForm"
            >
              {{ tm('cliConfigPage.confirm') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-snackbar v-model="snackbar" :color="snackColor" :timeout="4000">
        {{ snackMessage }}
      </v-snackbar>

      <DashboardStepUpDialog
        v-model="stepUpOpen"
        :loading="stepUpLoading"
        :error-message="stepUpError"
        @confirm="submitStepUp"
        @cancel="cancelStepUp"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import {
  codingCliApi,
  configProfileApi,
  type CodingCliKind,
  type CodingCliProvider,
  type CodingCliState,
  type OpenConfig,
} from '@/api/v1';
import ConfigDocsLink from '@/components/shared/ConfigDocsLink.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import FloatingActionStack from '@/components/ui/FloatingActionStack.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useModuleI18n } from '@/i18n/composables';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';
import {
  runConfigMutationWithStepUp,
  runMutationWithStepUp,
  stepUpHeaders,
} from '@/utils/stepUp';

defineOptions({ name: 'CliConfigPage' });

/** The action the switch route asks for; step-up is issued against it. */
const WRITE_ACTION = 'coding_cli.config.write';
/** The action the state route asks for: a read, which is rarely challenged. */
const READ_ACTION = 'platform.read';
/** The id the backend uses for the profile that is the running configuration. */
const SYSTEM_SCOPE = 'default';

/**
 * One stored provider.
 *
 * `api_key` is only ever what this page put there: the API reports whether a
 * key is stored, never the key itself, so a reload leaves this empty and an
 * empty field has to mean "leave the stored key alone".
 */
interface StoredProvider extends CodingCliProvider {
  cli: string;
  api_key: string;
}

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

const clis = ref<CodingCliState[]>([]);
const providers = ref<StoredProvider[]>([]);
const configData = ref<OpenConfig>({});
const loaded = ref(false);
const loadFailed = ref(false);
const saving = ref(false);
const busy = ref('');
const snackbar = ref(false);
const snackMessage = ref('');
const snackColor = ref<'success' | 'error'>('success');

const formOpen = ref(false);
const formEditing = ref(false);
const formError = ref('');
const showKey = ref(false);
const form = ref({
  cli: 'claude_code' satisfies CodingCliKind,
  id: '',
  name: '',
  base_url: '',
  api_key: '',
  model: '',
  note: '',
});

/** The list as last saved, so an edit can be told apart from the saved state. */
const savedProviders = ref('[]');
const dirty = computed(
  () => JSON.stringify(providers.value) !== savedProviders.value,
);

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

/** A short, safe reason for a failed request, for the operator to act on. */
function describeError(error: unknown): string {
  const response = (error as { response?: { data?: unknown } } | null)
    ?.response;
  const data = response?.data as { message?: unknown } | undefined;
  if (typeof data?.message === 'string' && data.message.trim()) {
    return data.message.trim();
  }
  if (error instanceof Error && error.message) return error.message;
  return '';
}

function cliLabel(cli: CodingCliKind) {
  return cli === 'codex'
    ? tm('cliConfigPage.codex')
    : tm('cliConfigPage.claudeCode');
}

function switchKey(cli: string, providerId: string) {
  return `switch:${cli}:${providerId}`;
}

function showSnack(message: string, color: 'success' | 'error') {
  snackMessage.value = message;
  snackColor.value = color;
  snackbar.value = true;
}

/** Staying is the safe answer: the unsaved list is the operator's own typing. */
function confirmLeaveIfNeeded() {
  if (!dirty.value) return true;
  return askForConfirmation(
    `${tm('cliConfigPage.unsavedTitle')}\n\n${tm('cliConfigPage.unsavedMessage')}`,
    confirmDialog,
  );
}

/** Whether this CLI's own file currently holds this provider. */
function isCurrent(state: CodingCliState, provider: CodingCliProvider) {
  if (!state.managed || !provider.base_url) return false;
  if (provider.base_url !== state.base_url) return false;
  return !provider.model || provider.model === state.model;
}

function providersFor(cli: CodingCliKind) {
  return providers.value.filter(
    (provider) => !provider.cli || provider.cli === cli,
  );
}

function find(id: string) {
  return providers.value.find((provider) => provider.id === id);
}

function nextId(base: string, cli: CodingCliKind): string {
  const taken = providersFor(cli).map((provider) => provider.id);
  if (!taken.includes(base)) return base;
  let suffix = 2;
  while (taken.includes(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

/** The raw stored list, so an entry keeps any field this page does not edit. */
function rawProviders(config: OpenConfig): Record<string, unknown>[] {
  const btw = (config as Record<string, unknown>).btw;
  const raw =
    btw && typeof btw === 'object' ? (btw as Record<string, unknown>) : {};
  return (Array.isArray(raw.cli_providers) ? raw.cli_providers : []).filter(
    (entry: unknown): entry is Record<string, unknown> =>
      entry !== null && typeof entry === 'object' && !Array.isArray(entry),
  );
}

async function load() {
  loadFailed.value = false;
  try {
    // The state call travels the step-up path even though a read is an ordinary
    // permission: a session that has not proved itself yet is answered with a
    // challenge, and without this the page would dead-end on a load error with
    // no way to answer it.
    const [stateResponse, profileResponse] = await Promise.all([
      runMutationWithStepUp(
        (stepUp) =>
          codingCliApi.state({ headers: stepUp ? stepUpHeaders(stepUp) : {} }),
        {
          action: READ_ACTION,
          resourceType: 'instance',
          resourceId: SYSTEM_SCOPE,
        },
        requestStepUp,
      ),
      configProfileApi.get(SYSTEM_SCOPE),
    ]);
    if (!stateResponse) {
      // The challenge was withdrawn, so there is nothing to show yet.
      loaded.value = false;
      loadFailed.value = true;
      return;
    }
    clis.value = stateResponse.data?.data?.clis ?? [];
    const payload = profileResponse.data?.data as
      Record<string, unknown> | undefined;
    const config = (payload?.config ?? {}) as OpenConfig;
    configData.value = config;
    providers.value = rawProviders(config).map((entry) => ({
      id: text(entry.id).trim(),
      name: text(entry.name).trim() || text(entry.id).trim(),
      base_url: text(entry.base_url).trim(),
      model: text(entry.model).trim(),
      note: text(entry.note).trim(),
      has_api_key: Boolean(text(entry.api_key).trim()),
      current: false,
      cli: text(entry.cli).trim(),
      api_key: text(entry.api_key),
    }));
    savedProviders.value = JSON.stringify(providers.value);
    loaded.value = true;
  } catch {
    loaded.value = false;
    loadFailed.value = true;
  }
}

async function save() {
  if (saving.value || !dirty.value) return;
  saving.value = true;
  const headers: Record<string, string> = {};
  try {
    // A deep copy through JSON, not structuredClone: the config is a reactive
    // proxy, and structuredClone refuses to clone one.  The value is plain
    // configuration, so a JSON round trip is the copy it wants.
    const config = JSON.parse(JSON.stringify(configData.value ?? {})) as Record<
      string,
      unknown
    >;
    const btw =
      config.btw && typeof config.btw === 'object'
        ? (config.btw as Record<string, unknown>)
        : {};
    const byId = new Map(
      rawProviders(configData.value).map((entry) => [
        text(entry.id).trim(),
        entry,
      ]),
    );
    btw.cli_providers = providers.value.map((provider) => {
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
      if (provider.api_key) entry.api_key = provider.api_key;
      else delete entry.api_key;
      return entry;
    });
    config.btw = btw;

    const response = await runConfigMutationWithStepUp(
      (stepUp) => {
        if (stepUp) Object.assign(headers, stepUpHeaders(stepUp));
        return configProfileApi.update(SYSTEM_SCOPE, config, {
          headers,
        });
      },
      SYSTEM_SCOPE,
      requestStepUp,
    );
    if (!response) return;
    savedProviders.value = JSON.stringify(providers.value);
    showSnack(tm('cliConfigPage.saved'), 'success');
  } catch (error: unknown) {
    // Say why: a swallowed reason here is how a broken save reads as a no-op.
    showSnack(
      `${tm('cliConfigPage.saveError')} ${describeError(error)}`,
      'error',
    );
  } finally {
    saving.value = false;
  }
}

function openForm(cli: CodingCliKind, provider?: CodingCliProvider) {
  formEditing.value = Boolean(provider);
  formError.value = '';
  showKey.value = false;
  form.value = {
    cli,
    id: provider?.id ?? nextId('provider', cli),
    name: provider?.name ?? '',
    base_url: provider?.base_url ?? '',
    api_key: '',
    model: provider?.model ?? '',
    note: provider?.note ?? '',
  };
  formOpen.value = true;
}

function confirmForm() {
  const id = form.value.id.trim();
  if (!id) {
    formError.value = tm('cliConfigPage.idRequired');
    return;
  }
  if (!form.value.base_url.trim() && !form.value.api_key.trim()) {
    formError.value = tm('cliConfigPage.endpointOrKeyRequired');
    return;
  }
  const scope = form.value.cli === 'claude_code' ? '' : form.value.cli;
  const clash = providers.value.some(
    (provider) => provider.id === id && (provider.cli ?? '') === scope,
  );
  const editingSelf =
    formEditing.value &&
    find(id) !== undefined &&
    (find(id)?.cli ?? '') === scope;
  if (clash && !editingSelf) {
    formError.value = tm('cliConfigPage.idTaken');
    return;
  }

  const apiKey = form.value.api_key.trim();
  const previous = find(id);
  const entry: StoredProvider = {
    id,
    name: form.value.name.trim() || id,
    base_url: form.value.base_url.trim(),
    model: form.value.model.trim(),
    note: form.value.note.trim(),
    has_api_key: Boolean(apiKey) || Boolean(previous?.has_api_key),
    current: false,
    cli: scope,
    api_key: apiKey || (previous?.api_key ?? ''),
  };

  const index = providers.value.findIndex((provider) => provider.id === id);
  const next = [...providers.value];
  if (index === -1) next.push(entry);
  else next[index] = entry;
  providers.value = next;
  formOpen.value = false;
}

function duplicate(cli: CodingCliKind, provider: CodingCliProvider) {
  const id = nextId(`${provider.id}-copy`, cli);
  const source = find(provider.id);
  providers.value = [
    ...providers.value,
    {
      ...provider,
      id,
      name: `${provider.name} (copy)`,
      current: false,
      cli: source?.cli ?? '',
      api_key: source?.api_key ?? '',
    },
  ];
}

async function remove(provider: CodingCliProvider) {
  const confirmed = await askForConfirmation(
    `${tm('cliConfigPage.deleteTitle')}\n\n${tm('cliConfigPage.deleteMessage')}`,
    confirmDialog,
  );
  if (!confirmed) return;
  providers.value = providers.value.filter((entry) => entry.id !== provider.id);
}

async function switchTo(state: CodingCliState, provider: CodingCliProvider) {
  const confirmed = await askForConfirmation(
    `${tm('cliConfigPage.switchTitle')}\n\n${tm('cliConfigPage.switchMessage')}`,
    confirmDialog,
  );
  if (!confirmed) return;

  busy.value = switchKey(state.cli, provider.id);
  try {
    const response = await runMutationWithStepUp(
      (stepUp) =>
        codingCliApi.switchProvider(
          { cli: state.cli, provider_id: provider.id },
          { headers: stepUp ? stepUpHeaders(stepUp) : {} },
        ),
      {
        action: WRITE_ACTION,
        resourceType: 'instance',
        resourceId: SYSTEM_SCOPE,
      },
      requestStepUp,
    );
    if (!response) return;
    showSnack(tm('cliConfigPage.switched'), 'success');
    await load();
  } catch (error: unknown) {
    // Say why: a swallowed reason here is how a broken save reads as a no-op.
    showSnack(
      `${tm('cliConfigPage.switchError')} ${describeError(error)}`,
      'error',
    );
  } finally {
    busy.value = '';
  }
}

async function restore(state: CodingCliState) {
  const confirmed = await askForConfirmation(
    `${tm('cliConfigPage.restoreTitle')}\n\n${tm('cliConfigPage.restoreMessage')}`,
    confirmDialog,
  );
  if (!confirmed) return;

  busy.value = `restore:${state.cli}`;
  try {
    const response = await runMutationWithStepUp(
      (stepUp) =>
        codingCliApi.remove(state.cli, {
          headers: stepUp ? stepUpHeaders(stepUp) : {},
        }),
      {
        action: WRITE_ACTION,
        resourceType: 'instance',
        resourceId: SYSTEM_SCOPE,
      },
      requestStepUp,
    );
    if (!response) return;
    showSnack(tm('cliConfigPage.restored'), 'success');
    await load();
  } catch (error: unknown) {
    // Say why: a swallowed reason here is how a broken save reads as a no-op.
    showSnack(
      `${tm('cliConfigPage.restoreError')} ${describeError(error)}`,
      'error',
    );
  } finally {
    busy.value = '';
  }
}

onBeforeRouteLeave(() => confirmLeaveIfNeeded());

onMounted(load);
</script>

<style scoped>
.cli-config-page {
  padding: 16px;
}

.cli-config-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.cli-config-page__title {
  font-size: 1.25rem;
  font-weight: 600;
}

.cli-config-page__subtitle {
  margin-top: 4px;
  opacity: 0.7;
  max-width: 70ch;
}

.cli-config-page__path code,
.cli-config-page__endpoint {
  word-break: break-all;
}

.cli-config-page__note {
  white-space: pre-wrap;
}

.cli-config-page__provider--current {
  border: 2px solid rgb(var(--v-theme-primary));
}
</style>

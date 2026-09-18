<!--
  Each coding CLI's global configuration, and the providers it can be switched
  between.

  The list is AstrBot configuration and travels through `v-model`, so the page
  saves it with the profile like any other setting.  Only the switch touches a
  file AstrBot does not own -- the CLI's own configuration -- so it asks for
  confirmation and a step-up credential.  It always acts on the running profile,
  which is the one the backend resolves the provider against.
-->
<template>
  <v-card class="coding-cli-providers" variant="outlined">
    <v-card-title class="text-body-1">
      {{ tm('thirdPartyAgentsPage.providersTitle') }}
    </v-card-title>

    <v-card-text>
      <p
        class="coding-cli-providers__subtitle text-body-2 text-medium-emphasis"
      >
        {{ tm('thirdPartyAgentsPage.providersSubtitle') }}
      </p>

      <v-alert class="mb-3" density="compact" variant="tonal" type="info">
        {{ tm('thirdPartyAgentsPage.delegatedHint') }}
      </v-alert>

      <v-alert
        v-if="loadFailed"
        class="coding-cli-providers__load-error mb-3"
        density="compact"
        variant="tonal"
        type="error"
      >
        {{ tm('thirdPartyAgentsPage.providersLoadError') }}
        <template #append>
          <v-btn size="small" variant="text" @click="load">
            {{ tm('thirdPartyAgentsPage.retry') }}
          </v-btn>
        </template>
      </v-alert>

      <v-skeleton-loader v-else-if="!loaded" type="article" />

      <template v-else>
        <v-card
          v-for="state in clis"
          :key="state.cli"
          class="coding-cli-providers__cli mb-6"
          variant="outlined"
        >
          <v-card-title class="d-flex align-center flex-wrap ga-2">
            <span class="text-body-1">{{ cliLabel(state.cli) }}</span>
            <v-chip
              v-if="state.managed"
              class="coding-cli-providers__managed"
              color="primary"
              size="small"
              variant="tonal"
              prepend-icon="mdi-check-circle-outline"
            >
              {{ tm('thirdPartyAgentsPage.managed') }}
            </v-chip>
            <v-chip
              v-if="state.has_credential"
              class="coding-cli-providers__credential"
              color="warning"
              size="small"
              variant="tonal"
              prepend-icon="mdi-key-outline"
            >
              {{ tm('thirdPartyAgentsPage.credentialStored') }}
            </v-chip>
            <v-spacer />
            <v-btn
              class="coding-cli-providers__add"
              color="primary"
              variant="tonal"
              size="small"
              prepend-icon="mdi-plus"
              @click="openForm(state.cli)"
            >
              {{ tm('thirdPartyAgentsPage.addProvider') }}
            </v-btn>
          </v-card-title>

          <v-card-text>
            <div class="coding-cli-providers__path">
              <code>{{ state.path }}</code>
            </div>
            <div class="text-body-2 text-medium-emphasis mb-3">
              {{
                state.exists
                  ? tm('thirdPartyAgentsPage.fileExists')
                  : tm('thirdPartyAgentsPage.fileAbsent')
              }}
            </div>

            <v-alert
              v-if="!providersFor(state.cli).length"
              class="coding-cli-providers__empty"
              density="compact"
              variant="tonal"
              type="info"
            >
              {{ tm('thirdPartyAgentsPage.noProviders') }}
            </v-alert>

            <v-row v-else density="compact">
              <v-col
                v-for="provider in providersFor(state.cli)"
                :key="provider.id"
                cols="12"
                md="6"
              >
                <v-card
                  class="coding-cli-providers__provider h-100"
                  variant="tonal"
                  :class="{
                    'coding-cli-providers__provider--current': isCurrent(
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
                        class="coding-cli-providers__current"
                        color="primary"
                        size="small"
                        variant="flat"
                        prepend-icon="mdi-check"
                      >
                        {{ tm('thirdPartyAgentsPage.current') }}
                      </v-chip>
                    </div>

                    <div class="coding-cli-providers__endpoint text-body-2">
                      {{
                        provider.base_url ||
                        tm('thirdPartyAgentsPage.noBaseUrl')
                      }}
                    </div>
                    <div
                      v-if="provider.model"
                      class="text-body-2 text-medium-emphasis"
                    >
                      {{ provider.model }}
                    </div>
                    <div
                      v-if="provider.note"
                      class="coding-cli-providers__note text-body-2 text-medium-emphasis"
                    >
                      {{ provider.note }}
                    </div>
                    <div class="text-body-2 text-medium-emphasis mt-1">
                      {{
                        provider.has_api_key
                          ? tm('thirdPartyAgentsPage.keyPresent')
                          : tm('thirdPartyAgentsPage.keyAbsent')
                      }}
                    </div>

                    <div class="d-flex align-center flex-wrap ga-1 mt-3">
                      <v-btn
                        class="coding-cli-providers__switch"
                        color="primary"
                        variant="flat"
                        size="small"
                        prepend-icon="mdi-swap-horizontal"
                        :aria-label="`${tm('thirdPartyAgentsPage.enable')}: ${provider.name}`"
                        :disabled="isCurrent(state, provider)"
                        :loading="busy === switchKey(state.cli, provider.id)"
                        @click="switchTo(state, provider)"
                      >
                        {{ tm('thirdPartyAgentsPage.enable') }}
                      </v-btn>
                      <v-btn
                        class="coding-cli-providers__edit"
                        variant="text"
                        size="small"
                        prepend-icon="mdi-pencil"
                        :aria-label="`${tm('thirdPartyAgentsPage.edit')}: ${provider.name}`"
                        @click="openForm(state.cli, provider)"
                      >
                        {{ tm('thirdPartyAgentsPage.edit') }}
                      </v-btn>
                      <v-btn
                        class="coding-cli-providers__duplicate"
                        variant="text"
                        size="small"
                        prepend-icon="mdi-content-copy"
                        :aria-label="`${tm('thirdPartyAgentsPage.duplicate')}: ${provider.name}`"
                        @click="duplicate(state.cli, provider)"
                      >
                        {{ tm('thirdPartyAgentsPage.duplicate') }}
                      </v-btn>
                      <v-btn
                        class="coding-cli-providers__delete"
                        color="error"
                        variant="text"
                        size="small"
                        prepend-icon="mdi-delete-outline"
                        :aria-label="`${tm('thirdPartyAgentsPage.delete')}: ${provider.name}`"
                        @click="remove(provider)"
                      >
                        {{ tm('thirdPartyAgentsPage.delete') }}
                      </v-btn>
                    </div>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>

            <div class="d-flex justify-end mt-2">
              <v-btn
                class="coding-cli-providers__restore"
                color="error"
                variant="text"
                size="small"
                prepend-icon="mdi-backup-restore"
                :disabled="!state.managed"
                :loading="busy === `restore:${state.cli}`"
                @click="restore(state)"
              >
                {{ tm('thirdPartyAgentsPage.restore') }}
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </template>
    </v-card-text>

    <v-dialog v-model="formOpen" max-width="640">
      <v-card>
        <v-card-title>
          {{
            formEditing
              ? tm('thirdPartyAgentsPage.editProvider')
              : tm('thirdPartyAgentsPage.addProvider')
          }}
        </v-card-title>
        <v-card-text>
          <v-row density="compact">
            <v-col cols="12" sm="6">
              <v-text-field
                class="coding-cli-providers__form-id"
                :model-value="form.id"
                :label="tm('thirdPartyAgentsPage.providerId')"
                :hint="tm('thirdPartyAgentsPage.providerIdHint')"
                persistent-hint
                density="compact"
                variant="outlined"
                @update:model-value="form.id = text($event)"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                class="coding-cli-providers__form-name"
                :model-value="form.name"
                :label="tm('thirdPartyAgentsPage.providerName')"
                :placeholder="form.id"
                density="compact"
                variant="outlined"
                hide-details
                @update:model-value="form.name = text($event)"
              />
            </v-col>
            <v-col cols="12">
              <v-text-field
                class="coding-cli-providers__form-base-url"
                :model-value="form.base_url"
                :label="tm('thirdPartyAgentsPage.baseUrl')"
                :hint="
                  form.cli === 'codex'
                    ? tm('thirdPartyAgentsPage.baseUrlHintCodex')
                    : tm('thirdPartyAgentsPage.baseUrlHintClaude')
                "
                persistent-hint
                density="compact"
                variant="outlined"
                @update:model-value="form.base_url = text($event)"
              />
            </v-col>
            <v-col cols="12">
              <v-text-field
                class="coding-cli-providers__form-api-key"
                :model-value="form.api_key"
                :type="showKey ? 'text' : 'password'"
                :label="tm('thirdPartyAgentsPage.apiKey')"
                :hint="tm('thirdPartyAgentsPage.apiKeyHint')"
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
                class="coding-cli-providers__form-model"
                :model-value="form.model"
                :label="tm('thirdPartyAgentsPage.model')"
                :hint="tm('thirdPartyAgentsPage.modelHint')"
                persistent-hint
                density="compact"
                variant="outlined"
                @update:model-value="form.model = text($event)"
              />
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                class="coding-cli-providers__form-note"
                :model-value="form.note"
                :label="tm('thirdPartyAgentsPage.note')"
                density="compact"
                variant="outlined"
                hide-details
                @update:model-value="form.note = text($event)"
              />
            </v-col>
          </v-row>
          <v-alert
            v-if="formError"
            class="coding-cli-providers__form-error mt-3"
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
            {{ tm('thirdPartyAgentsPage.cancel') }}
          </v-btn>
          <v-btn
            class="coding-cli-providers__form-confirm"
            color="primary"
            variant="tonal"
            @click="confirmForm"
          >
            {{ tm('thirdPartyAgentsPage.confirm') }}
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
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  codingCliApi,
  type CodingCliKind,
  type CodingCliProvider,
  type CodingCliState,
  type StoredCliProvider,
} from '@/api/v1';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useModuleI18n } from '@/i18n/composables';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';
import { runMutationWithStepUp, stepUpHeaders } from '@/utils/stepUp';

defineOptions({ name: 'CodingCliProviders' });

/** The action the switch route asks for; step-up is issued against it. */
const WRITE_ACTION = 'coding_cli.config.write';
/** The action the state route asks for: a read, which is rarely challenged. */
const READ_ACTION = 'platform.read';
/** The id the backend resolves the provider against, on every switch. */
const RUNNING_SCOPE = 'default';

const props = withDefaults(
  defineProps<{
    /** The stored provider list, edited in place through `update:modelValue`. */
    modelValue?: StoredCliProvider[];
  }>(),
  { modelValue: () => [] },
);

const emit = defineEmits<{
  'update:modelValue': [value: StoredCliProvider[]];
}>();

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
const loaded = ref(false);
const loadFailed = ref(false);
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

const providers = computed(() => props.modelValue);

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
    ? tm('thirdPartyAgentsPage.codex')
    : tm('thirdPartyAgentsPage.claudeCode');
}

function switchKey(cli: string, providerId: string) {
  return `switch:${cli}:${providerId}`;
}

function showSnack(message: string, color: 'success' | 'error') {
  snackMessage.value = message;
  snackColor.value = color;
  snackbar.value = true;
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

function commit(next: StoredCliProvider[]) {
  emit('update:modelValue', next);
}

function nextId(base: string, cli: CodingCliKind): string {
  const taken = providersFor(cli).map((provider) => provider.id);
  if (!taken.includes(base)) return base;
  let suffix = 2;
  while (taken.includes(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

async function load() {
  loadFailed.value = false;
  try {
    // Through the step-up path even though a read is an ordinary permission: a
    // session that has not proved itself yet is answered with a challenge, and
    // without this the page would dead-end on a button that cannot elevate.
    const response = await runMutationWithStepUp(
      (stepUp) =>
        codingCliApi.state({ headers: stepUp ? stepUpHeaders(stepUp) : {} }),
      {
        action: READ_ACTION,
        resourceType: 'instance',
        resourceId: RUNNING_SCOPE,
      },
      requestStepUp,
    );
    if (!response) {
      // The challenge was withdrawn, so there is nothing to show yet.
      loaded.value = false;
      loadFailed.value = true;
      return;
    }
    clis.value = response.data?.data?.clis ?? [];
    loaded.value = true;
  } catch {
    loaded.value = false;
    loadFailed.value = true;
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
    formError.value = tm('thirdPartyAgentsPage.idRequired');
    return;
  }
  if (!form.value.base_url.trim() && !form.value.api_key.trim()) {
    formError.value = tm('thirdPartyAgentsPage.endpointOrKeyRequired');
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
    formError.value = tm('thirdPartyAgentsPage.idTaken');
    return;
  }

  const apiKey = form.value.api_key.trim();
  const previous = find(id);
  const entry: StoredCliProvider = {
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
  commit(next);
  formOpen.value = false;
}

function duplicate(cli: CodingCliKind, provider: CodingCliProvider) {
  const id = nextId(`${provider.id}-copy`, cli);
  const source = find(provider.id);
  commit([
    ...providers.value,
    {
      ...provider,
      id,
      name: `${provider.name} (copy)`,
      current: false,
      cli: source?.cli ?? '',
      api_key: source?.api_key ?? '',
    },
  ]);
}

async function remove(provider: CodingCliProvider) {
  const confirmed = await askForConfirmation(
    `${tm('thirdPartyAgentsPage.deleteTitle')}\n\n${tm('thirdPartyAgentsPage.deleteMessage')}`,
    confirmDialog,
  );
  if (!confirmed) return;
  commit(providers.value.filter((entry) => entry.id !== provider.id));
}

async function switchTo(state: CodingCliState, provider: CodingCliProvider) {
  const confirmed = await askForConfirmation(
    `${tm('thirdPartyAgentsPage.switchTitle')}\n\n${tm('thirdPartyAgentsPage.switchMessage')}`,
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
        resourceId: RUNNING_SCOPE,
      },
      requestStepUp,
    );
    if (!response) return;
    showSnack(tm('thirdPartyAgentsPage.switched'), 'success');
    await load();
  } catch (error: unknown) {
    // Say why: a swallowed reason here is how a broken switch reads as a no-op.
    showSnack(
      `${tm('thirdPartyAgentsPage.switchError')} ${describeError(error)}`,
      'error',
    );
  } finally {
    busy.value = '';
  }
}

async function restore(state: CodingCliState) {
  const confirmed = await askForConfirmation(
    `${tm('thirdPartyAgentsPage.restoreTitle')}\n\n${tm('thirdPartyAgentsPage.restoreMessage')}`,
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
        resourceId: RUNNING_SCOPE,
      },
      requestStepUp,
    );
    if (!response) return;
    showSnack(tm('thirdPartyAgentsPage.restored'), 'success');
    await load();
  } catch (error: unknown) {
    // Say why: a swallowed reason here is how a broken restore reads as a no-op.
    showSnack(
      `${tm('thirdPartyAgentsPage.restoreError')} ${describeError(error)}`,
      'error',
    );
  } finally {
    busy.value = '';
  }
}

onMounted(load);
</script>

<style scoped>
.coding-cli-providers__subtitle {
  margin-bottom: 12px;
  max-width: 90ch;
}

.coding-cli-providers__path code,
.coding-cli-providers__endpoint {
  word-break: break-all;
}

.coding-cli-providers__note {
  white-space: pre-wrap;
}

.coding-cli-providers__provider--current {
  border: 2px solid rgb(var(--v-theme-primary));
}
</style>

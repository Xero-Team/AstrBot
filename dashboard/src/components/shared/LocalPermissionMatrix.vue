<template>
  <div class="local-permission-matrix">
    <v-progress-linear
      v-if="runtimeLoading && !runtime"
      indeterminate
      color="primary"
    />
    <v-alert
      v-else-if="!runtime"
      type="warning"
      variant="tonal"
      density="compact"
    >
      {{ tm('runtimeUnknown') }}
    </v-alert>

    <v-table class="permission-table">
      <thead>
        <tr>
          <th scope="col">{{ tm('role') }}</th>
          <th scope="col" class="text-center">{{ tm('execution') }}</th>
          <th scope="col" class="text-center">{{ tm('network') }}</th>
          <th scope="col" class="text-center">{{ tm('filesystem') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="role in roles" :key="role" :aria-label="tm(`roles.${role}`)">
          <th scope="row">{{ tm(`roles.${role}`) }}</th>
          <td>
            <div class="execution-cell">
              <v-checkbox-btn
                :model-value="policy(role, false).allow_execution"
                :disabled="permissionLocks[role].execution"
                :aria-label="`${tm(`roles.${role}`)} · ${tm('execution')}`"
                color="primary"
                density="compact"
                @update:model-value="
                  updatePermission(role, { allow_execution: Boolean($event) })
                "
              />
              <span
                v-if="executionBlockedRoles.includes(role)"
                class="execution-status text-warning text-caption"
              >
                {{ tm('executionInactive') }}
                <v-tooltip
                  location="top"
                  open-on-click
                  :max-width="480"
                  :text="
                    tm('executionBlocked', {
                      role: tm(`roles.${role}`),
                      reason: isolationFailureReason,
                    })
                  "
                >
                  <template #activator="{ props: helpProps }">
                    <button
                      v-bind="helpProps"
                      type="button"
                      class="scope-help"
                      :aria-label="tm('executionInactiveHelp')"
                    >
                      <v-icon size="14" aria-hidden="true"
                        >mdi-help-circle-outline</v-icon
                      >
                    </button>
                  </template>
                </v-tooltip>
              </span>
            </div>
          </td>
          <td>
            <div class="network-cell">
              <v-select
                :model-value="policy(role, false).network.mode"
                :items="networkModeItems"
                :disabled="!runtime || !policy(role, false).allow_execution"
                :aria-label="`${tm(`roles.${role}`)} · ${tm('network')}`"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="
                  updatePermission(role, {
                    network: { ...policy(role, false).network, mode: $event },
                  })
                "
              />
              <v-btn
                variant="text"
                size="small"
                :disabled="
                  !runtime ||
                  !policy(role, false).allow_execution ||
                  policy(role, false).network.mode === 'off'
                "
                @click="openNetworkDialog(role)"
              >
                {{ tm('networkRules') }}
              </v-btn>
            </div>
          </td>
          <td>
            <div class="filesystem-cell">
              <v-select
                :model-value="policy(role, false).filesystem_scope"
                :items="scopeItems"
                :disabled="!runtime"
                :aria-label="`${tm(`roles.${role}`)} · ${tm('filesystem')}`"
                variant="outlined"
                density="compact"
                hide-details
                @update:model-value="
                  updatePermission(role, { filesystem_scope: $event })
                "
              />
              <v-btn
                variant="text"
                size="small"
                :disabled="!runtime"
                @click="openFilesystemDialog(role)"
              >
                {{ tm('denyRules') }}
              </v-btn>
              <v-btn
                variant="text"
                size="small"
                :disabled="!runtime"
                @click="openSocketDialog(role)"
              >
                {{ tm('socketRules') }}
              </v-btn>
            </div>
          </td>
        </tr>
      </tbody>
    </v-table>

    <v-alert
      v-if="memberHasElevatedAccess"
      type="warning"
      variant="tonal"
      density="compact"
    >
      {{ tm('memberWarning') }}
    </v-alert>
    <v-alert
      v-if="hasNativePolicy"
      type="warning"
      variant="tonal"
      density="compact"
    >
      {{ tm('nativeWarning') }}
    </v-alert>
    <v-alert
      v-if="hasDenyGlob && isLinux"
      type="info"
      variant="tonal"
      density="compact"
    >
      {{ tm('globWarning') }}
    </v-alert>
    <v-alert type="info" variant="tonal" density="compact">
      {{ tm('hardLinkWarning') }}
    </v-alert>

    <v-dialog v-model="networkDialog" max-width="560">
      <v-card>
        <v-card-title>{{ tm('networkDialog.title') }}</v-card-title>
        <v-card-text>
          <v-checkbox
            v-model="draft.allow_private_network"
            :label="tm('networkDialog.private')"
            density="compact"
          />
          <v-checkbox
            v-model="draft.allow_loopback"
            :label="tm('networkDialog.loopback')"
            density="compact"
          />
          <v-textarea
            v-model="draft.allowed_domains"
            :label="tm('networkDialog.allowed')"
            :hint="tm('networkDialog.hint')"
            :rules="[domainFieldRules]"
            persistent-hint
            rows="4"
            variant="outlined"
          />
          <v-textarea
            v-model="draft.denied_domains"
            :label="tm('networkDialog.denied')"
            :rules="[domainFieldRules]"
            rows="4"
            variant="outlined"
          />
          <v-alert
            v-for="error in dialogErrors"
            :key="error"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-2"
          >
            {{ error }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="networkDialog = false">
            {{ tm('dialog.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :disabled="dialogErrors.length > 0"
            @click="saveNetworkDialog"
          >
            {{ tm('dialog.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="filesystemDialog" max-width="560">
      <v-card>
        <v-card-title>{{ tm('filesystemDialog.title') }}</v-card-title>
        <v-card-text>
          <v-textarea
            v-model="draft.deny_read"
            :label="tm('filesystemDialog.read')"
            :hint="tm('filesystemDialog.hint')"
            :rules="[pathFieldRules]"
            persistent-hint
            rows="4"
            variant="outlined"
          />
          <v-textarea
            v-model="draft.deny_write"
            :label="tm('filesystemDialog.write')"
            :rules="[pathFieldRules]"
            rows="4"
            variant="outlined"
          />
          <v-alert
            v-for="error in dialogErrors"
            :key="error"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-2"
          >
            {{ error }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="filesystemDialog = false">
            {{ tm('dialog.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :disabled="dialogErrors.length > 0"
            @click="saveFilesystemDialog"
          >
            {{ tm('dialog.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="socketDialog" max-width="560">
      <v-card>
        <v-card-title>{{ tm('socketDialog.title') }}</v-card-title>
        <v-card-text>
          <v-alert
            v-if="policy(dialogRole, false).network.mode === 'off'"
            type="info"
            variant="tonal"
            density="compact"
          >
            {{ tm('socketDialog.offHint') }}
          </v-alert>
          <v-select
            v-model="draft.socket_mode"
            :items="socketModeItems"
            :label="tm('socketDialog.mode')"
            variant="outlined"
            density="compact"
          />
          <v-textarea
            v-if="isMacOS && draft.socket_mode === 'deny'"
            v-model="draft.allowed_paths"
            :label="tm('socketDialog.paths')"
            :hint="tm('socketDialog.macHint')"
            :rules="[socketPathFieldRules]"
            persistent-hint
            rows="3"
            variant="outlined"
          />
          <v-alert v-else type="info" variant="tonal" density="compact">
            {{ tm('socketDialog.linuxHint') }}
          </v-alert>
          <v-alert
            v-for="error in dialogErrors"
            :key="error"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-2"
          >
            {{ error }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="socketDialog = false">
            {{ tm('dialog.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :disabled="dialogErrors.length > 0"
            @click="saveSocketDialog"
          >
            {{ tm('dialog.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script lang="ts">
import {
  type PermissionPolicy,
  isNativePolicy,
  requiresSandbox,
} from '@/utils/localPermissionRules';

export const localPermissionDefaults: Record<
  'member' | 'admin',
  PermissionPolicy
> = {
  member: {
    filesystem_scope: 'workspace',
    allow_execution: false,
    network: {
      mode: 'off',
      allowed_domains: [],
      denied_domains: [],
      allow_private_network: false,
      allow_loopback: false,
    },
    filesystem: { deny_read: [], deny_write: [] },
    unix_sockets: { mode: 'deny', allowed_paths: [] },
  },
  admin: {
    filesystem_scope: 'host',
    allow_execution: true,
    network: {
      mode: 'unrestricted',
      allowed_domains: [],
      denied_domains: [],
      allow_private_network: true,
      allow_loopback: true,
    },
    filesystem: { deny_read: [], deny_write: [] },
    unix_sockets: { mode: 'allow_all', allowed_paths: [] },
  },
};
</script>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type { PropType } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { statsApi } from '@/api/v1';
import type { RuntimeInfo } from '@/api/v1';
import {
  MAX_DOMAIN_RULES,
  MAX_PATH_RULES,
  MAX_UNIX_PATHS,
  boundedErrors,
  normalizePolicy,
  normalizeRules,
  parseRuleLines,
  validateDomainRule,
  validatePathRule,
  validateUnixPathRule,
} from '@/utils/localPermissionRules';

type PermissionRole = 'member' | 'admin';
type PermissionModelValue = Partial<
  Record<PermissionRole, Partial<PermissionPolicy>>
>;

const props = defineProps({
  modelValue: {
    type: Object as PropType<PermissionModelValue>,
    default: () => ({}),
  },
});

const emit = defineEmits(['update:modelValue']);
const { tm } = useModuleI18n(
  'features/config-metadata.ai_group.agent_computer_use.local_permissions',
);
const runtime = ref<RuntimeInfo | null>(null);
const runtimeLoading = ref(true);
const networkDialog = ref(false);
const filesystemDialog = ref(false);
const socketDialog = ref(false);
const dialogRole = ref<PermissionRole>('member');
const dialogErrors = ref<string[]>([]);
const draft = reactive<{
  allowed_domains: string;
  denied_domains: string;
  allow_private_network: boolean;
  allow_loopback: boolean;
  deny_read: string;
  deny_write: string;
  socket_mode: 'deny' | 'allow_all';
  allowed_paths: string;
}>({
  allowed_domains: '',
  denied_domains: '',
  allow_private_network: false,
  allow_loopback: false,
  deny_read: '',
  deny_write: '',
  socket_mode: 'deny',
  allowed_paths: '',
});
const roles: PermissionRole[] = ['member', 'admin'];
const defaults = computed(() => localPermissionDefaults);

const platform = computed(() => runtime.value?.os || '');
const isLinux = computed(() => platform.value === 'linux');
const isMacOS = computed(() => platform.value === 'darwin');
const unsupported = computed(
  () => runtime.value?.sandbox?.status === 'unsupported',
);
const sandboxUnavailable = computed(() => {
  const status = runtime.value?.sandbox?.status;
  return status === 'missing' || status === 'unavailable';
});
const isolationUnavailable = computed(
  () => unsupported.value || sandboxUnavailable.value,
);
const isolationFailureReason = computed(() => {
  const current = runtime.value;
  if (!isolationUnavailable.value || !current) return '';
  const reason = tm(`runtime.isolationFailure.${current.sandbox.status}`, {
    backend: current.sandbox.backend === 'seatbelt' ? 'Seatbelt' : 'bubblewrap',
    dependency:
      current.sandbox.backend === 'seatbelt' ? 'sandbox-exec' : 'bwrap',
  });
  return current.sandbox.error ? `${reason} ${current.sandbox.error}` : reason;
});
const networkModeItems = computed(() => [
  { title: tm('modes.off'), value: 'off' },
  { title: tm('modes.allowlist'), value: 'allowlist' },
  { title: tm('modes.unrestricted'), value: 'unrestricted' },
]);
const socketModeItems = computed(() => [
  { title: tm('sockets.deny'), value: 'deny' },
  { title: tm('sockets.allowAll'), value: 'allow_all' },
]);
const scopeItems = computed(() => [
  { title: tm('modes.none'), value: 'none' },
  { title: tm('scopes.workspace'), value: 'workspace' },
  { title: tm('scopes.host'), value: 'host' },
]);

onMounted(async () => {
  try {
    const response = await statsApi.version();
    runtime.value = response.data?.data?.runtime ?? null;
  } catch (error) {
    console.warn('Failed to load runtime information:', error);
  } finally {
    runtimeLoading.value = false;
  }
});

function policy(role: PermissionRole, applyRuntime = true): PermissionPolicy {
  const resolved = normalizePolicy(
    props.modelValue?.[role],
    defaults.value[role],
  );
  if (applyRuntime && isolationUnavailable.value && requiresSandbox(resolved)) {
    return {
      ...resolved,
      allow_execution: false,
      network: { ...resolved.network, mode: 'off' },
      unix_sockets: {
        ...resolved.unix_sockets,
        mode: 'deny',
        allowed_paths: [],
      },
    };
  }
  return resolved;
}

function updatePermission(
  role: PermissionRole,
  changes: Partial<PermissionPolicy>,
): void {
  const current = normalizePolicy(
    props.modelValue?.[role],
    defaults.value[role],
  );
  const updated = normalizePolicy(
    {
      ...current,
      ...changes,
      network: { ...current.network, ...(changes.network || {}) },
      filesystem: { ...current.filesystem, ...(changes.filesystem || {}) },
      unix_sockets: {
        ...current.unix_sockets,
        ...(changes.unix_sockets || {}),
      },
    },
    defaults.value[role],
  );
  emit('update:modelValue', {
    ...(props.modelValue || {}),
    [role]: updated,
  });
}

function fillDraft(role: PermissionRole): void {
  const current = policy(role, false);
  draft.allowed_domains = current.network.allowed_domains.join('\n');
  draft.denied_domains = current.network.denied_domains.join('\n');
  draft.allow_private_network = current.network.allow_private_network;
  draft.allow_loopback = current.network.allow_loopback;
  draft.deny_read = current.filesystem.deny_read.join('\n');
  draft.deny_write = current.filesystem.deny_write.join('\n');
  draft.socket_mode = current.unix_sockets.mode;
  draft.allowed_paths = current.unix_sockets.allowed_paths.join('\n');
  dialogErrors.value = [];
}

function domainFieldRules(value: string): true | string {
  const result = normalizeRules(
    parseRuleLines(value),
    validateDomainRule,
    MAX_DOMAIN_RULES,
  );
  return result.errors[0] ?? true;
}

function pathFieldRules(value: string): true | string {
  const result = normalizeRules(
    parseRuleLines(value),
    (rule) => validatePathRule(rule, platform.value),
    MAX_PATH_RULES,
  );
  return result.errors[0] ?? true;
}

function socketPathFieldRules(value: string): true | string {
  if (!isMacOS.value) return true;
  const result = normalizeRules(
    parseRuleLines(value),
    (rule) => validateUnixPathRule(rule, platform.value),
    MAX_UNIX_PATHS,
  );
  return result.errors[0] ?? true;
}

function openNetworkDialog(role: PermissionRole): void {
  dialogRole.value = role;
  fillDraft(role);
  validateNetworkDraft();
  networkDialog.value = true;
}

function openFilesystemDialog(role: PermissionRole): void {
  dialogRole.value = role;
  fillDraft(role);
  validateFilesystemDraft();
  filesystemDialog.value = true;
}

function openSocketDialog(role: PermissionRole): void {
  dialogRole.value = role;
  fillDraft(role);
  validateSocketDraft();
  socketDialog.value = true;
}

function validateNetworkDraft(): void {
  const errors: string[] = [];
  const allowed = normalizeRules(
    parseRuleLines(draft.allowed_domains),
    validateDomainRule,
    MAX_DOMAIN_RULES,
  );
  const denied = normalizeRules(
    parseRuleLines(draft.denied_domains),
    validateDomainRule,
    MAX_DOMAIN_RULES,
  );
  errors.push(...allowed.errors, ...denied.errors);
  dialogErrors.value = boundedErrors(errors);
}

function validateFilesystemDraft(): void {
  const options = { platform: platform.value };
  const read = normalizeRules(
    parseRuleLines(draft.deny_read),
    (rule) => validatePathRule(rule, options.platform),
    MAX_PATH_RULES,
  );
  const write = normalizeRules(
    parseRuleLines(draft.deny_write),
    (rule) => validatePathRule(rule, options.platform),
    MAX_PATH_RULES,
  );
  dialogErrors.value = boundedErrors([...read.errors, ...write.errors]);
}

function validateSocketDraft(): void {
  if (!isMacOS.value) {
    dialogErrors.value = [];
    return;
  }
  const paths = normalizeRules(
    parseRuleLines(draft.allowed_paths),
    (rule) => validateUnixPathRule(rule, platform.value),
    MAX_UNIX_PATHS,
  );
  dialogErrors.value = boundedErrors(paths.errors);
}

function saveNetworkDialog(): void {
  validateNetworkDraft();
  if (dialogErrors.value.length > 0) return;
  updatePermission(dialogRole.value, {
    network: {
      ...policy(dialogRole.value, false).network,
      allowed_domains: parseRuleLines(draft.allowed_domains),
      denied_domains: parseRuleLines(draft.denied_domains),
      allow_private_network: draft.allow_private_network,
      allow_loopback: draft.allow_loopback,
    },
  });
  networkDialog.value = false;
}

function saveFilesystemDialog(): void {
  validateFilesystemDraft();
  if (dialogErrors.value.length > 0) return;
  updatePermission(dialogRole.value, {
    filesystem: {
      deny_read: parseRuleLines(draft.deny_read),
      deny_write: parseRuleLines(draft.deny_write),
    },
  });
  filesystemDialog.value = false;
}

function saveSocketDialog(): void {
  validateSocketDraft();
  if (dialogErrors.value.length > 0) return;
  updatePermission(dialogRole.value, {
    unix_sockets: {
      mode: draft.socket_mode,
      allowed_paths: isMacOS.value ? parseRuleLines(draft.allowed_paths) : [],
    },
  });
  socketDialog.value = false;
}

const executionBlockedRoles = computed(() =>
  roles.filter(
    (role) =>
      isolationUnavailable.value &&
      policy(role, false).allow_execution &&
      requiresSandbox(policy(role, false)),
  ),
);
const hasNativePolicy = computed(() =>
  roles.some((role) => isNativePolicy(policy(role, false))),
);
const hasDenyGlob = computed(() =>
  roles.some((role) =>
    [
      ...policy(role, false).filesystem.deny_read,
      ...policy(role, false).filesystem.deny_write,
    ].some((rule) => /[*?[]/.test(rule)),
  ),
);
const permissionLocks = computed(() =>
  Object.fromEntries(
    roles.map((role) => {
      const current = policy(role, false);
      return [
        role,
        {
          execution: !runtime.value || current.filesystem_scope === 'none',
          network: !runtime.value || !current.allow_execution,
        },
      ];
    }),
  ),
);
const memberHasElevatedAccess = computed(() => {
  const member = policy('member');
  return member.network.mode !== 'off' || member.filesystem_scope === 'host';
});
</script>

<style scoped>
.local-permission-matrix {
  display: grid;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding-top: 12px;
}
.permission-table {
  min-width: 0;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
  border-radius: 8px;
}
.permission-table :deep(table) {
  table-layout: fixed;
}
.execution-cell,
.network-cell,
.filesystem-cell {
  display: grid;
  gap: 2px;
  justify-items: start;
}
.execution-cell {
  grid-auto-flow: column;
  align-items: center;
}
.scope-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: inherit;
  cursor: help;
}
</style>

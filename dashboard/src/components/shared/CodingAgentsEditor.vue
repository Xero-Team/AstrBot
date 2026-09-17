<!--
  Editor for `btw.work_loop.coding_agents`.

  The value is a list of objects, which the generic list editor cannot hold, so
  this component owns the shape.  The enums below mirror the ones the backend
  enforces in `astrbot/core/agent/btw/coding_agents.py`; that module stays the
  source of truth, and a change there has to be mirrored here.

  Nothing is emitted until the operator edits something.  The configuration page
  treats a change to the profile as unsaved work, so normalizing on load would
  raise that banner before anyone typed.
-->
<template>
  <div class="coding-agents-editor">
    <v-alert density="compact" variant="tonal" type="info" class="mb-3">
      {{ tm('codingAgentsEditor.hint') }}
    </v-alert>

    <div class="d-flex justify-end mb-2">
      <v-btn
        class="coding-agents-editor__add-agent"
        color="primary"
        variant="tonal"
        size="small"
        prepend-icon="mdi-plus"
        @click="addAgent"
      >
        {{ tm('codingAgentsEditor.addAgent') }}
      </v-btn>
    </div>

    <v-alert
      v-if="!entries.length"
      class="coding-agents-editor__empty"
      density="compact"
      variant="tonal"
      type="info"
    >
      {{ tm('codingAgentsEditor.empty') }}
    </v-alert>

    <v-card
      v-for="(entry, index) in entries"
      :key="index"
      class="coding-agents-editor__agent mb-4"
      variant="outlined"
    >
      <v-card-title
        class="d-flex align-center justify-space-between flex-wrap ga-2"
      >
        <div class="d-flex align-center ga-2">
          <v-switch
            class="coding-agents-editor__enabled"
            :model-value="entry.enabled"
            color="primary"
            density="compact"
            hide-details
            inset
            :label="tm('codingAgentsEditor.enabled')"
            @update:model-value="
              patchAgent(index, { enabled: $event === true })
            "
          />
          <span class="text-body-1">
            {{ entry.name || entry.id || tm('codingAgentsEditor.newAgent') }}
          </span>
        </div>
        <div class="d-flex align-center">
          <v-btn
            class="coding-agents-editor__move-up"
            icon="mdi-arrow-up"
            size="small"
            variant="text"
            :disabled="index === 0"
            :title="tm('codingAgentsEditor.moveUp')"
            @click="moveAgent(index, -1)"
          />
          <v-btn
            class="coding-agents-editor__move-down"
            icon="mdi-arrow-down"
            size="small"
            variant="text"
            :disabled="index === entries.length - 1"
            :title="tm('codingAgentsEditor.moveDown')"
            @click="moveAgent(index, 1)"
          />
          <v-btn
            class="coding-agents-editor__remove-agent"
            icon="mdi-delete"
            size="small"
            variant="text"
            color="error"
            :title="tm('codingAgentsEditor.removeAgent')"
            @click="removeAgent(index)"
          />
        </div>
      </v-card-title>

      <v-card-text>
        <v-alert
          v-for="warning in warningsFor(index)"
          :key="warning"
          class="coding-agents-editor__warning mb-2"
          density="compact"
          variant="tonal"
          type="warning"
        >
          {{ warning }}
        </v-alert>

        <v-row density="compact">
          <v-col cols="12" sm="6">
            <v-text-field
              class="coding-agents-editor__id"
              :model-value="entry.id"
              :label="tm('codingAgentsEditor.agentId')"
              :hint="tm('codingAgentsEditor.agentIdHint')"
              persistent-hint
              density="compact"
              variant="outlined"
              @update:model-value="patchAgent(index, { id: text($event) })"
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              class="coding-agents-editor__name"
              :model-value="entry.name"
              :label="tm('codingAgentsEditor.agentName')"
              :placeholder="entry.id"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="patchAgent(index, { name: text($event) })"
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-select
              class="coding-agents-editor__type"
              :model-value="entry.type"
              :items="TYPE_OPTIONS"
              :label="tm('codingAgentsEditor.agentType')"
              density="compact"
              variant="outlined"
              hide-details
              @update:model-value="setType(index, $event)"
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              class="coding-agents-editor__command"
              :model-value="entry.command"
              :label="tm('codingAgentsEditor.command')"
              :placeholder="DEFAULT_COMMANDS[entry.type]"
              :hint="tm('codingAgentsEditor.commandHint')"
              persistent-hint
              density="compact"
              variant="outlined"
              @update:model-value="patchAgent(index, { command: text($event) })"
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              class="coding-agents-editor__model"
              :model-value="entry.model"
              :label="tm('codingAgentsEditor.model')"
              :hint="tm('codingAgentsEditor.modelHint')"
              persistent-hint
              density="compact"
              variant="outlined"
              @update:model-value="patchAgent(index, { model: text($event) })"
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              class="coding-agents-editor__project-dir"
              :model-value="entry.project_dir"
              :label="tm('codingAgentsEditor.projectDir')"
              :hint="tm('codingAgentsEditor.projectDirHint')"
              persistent-hint
              density="compact"
              variant="outlined"
              @update:model-value="
                patchAgent(index, { project_dir: text($event) })
              "
            />
          </v-col>
          <v-col v-if="entry.type === 'claude_code'" cols="12" sm="6">
            <v-select
              class="coding-agents-editor__permission-mode"
              :model-value="entry.permission_mode"
              :items="CLAUDE_PERMISSION_MODES"
              :label="tm('codingAgentsEditor.permissionMode')"
              :hint="tm('codingAgentsEditor.permissionModeHint')"
              persistent-hint
              density="compact"
              variant="outlined"
              @update:model-value="
                patchAgent(index, {
                  permission_mode: enumOr(
                    $event,
                    CLAUDE_PERMISSION_MODES,
                    DEFAULT_PERMISSION_MODE,
                  ),
                })
              "
            />
          </v-col>
          <v-col v-if="entry.type === 'codex'" cols="12" sm="6">
            <v-select
              class="coding-agents-editor__sandbox"
              :model-value="entry.sandbox"
              :items="CODEX_SANDBOXES"
              :label="tm('codingAgentsEditor.sandbox')"
              :hint="tm('codingAgentsEditor.sandboxHint')"
              persistent-hint
              density="compact"
              variant="outlined"
              @update:model-value="
                patchAgent(index, {
                  sandbox: enumOr($event, CODEX_SANDBOXES, DEFAULT_SANDBOX),
                })
              "
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              class="coding-agents-editor__timeout"
              :model-value="entry.timeout_seconds"
              type="number"
              :min="MIN_TIMEOUT_SECONDS"
              :label="tm('codingAgentsEditor.timeoutSeconds')"
              density="compact"
              variant="outlined"
              hide-details
              @blur="
                commitNumber(
                  index,
                  'timeout_seconds',
                  $event,
                  MIN_TIMEOUT_SECONDS,
                  DEFAULT_TIMEOUT_SECONDS,
                )
              "
            />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              class="coding-agents-editor__max-output"
              :model-value="entry.max_output_chars"
              type="number"
              :min="MIN_MAX_OUTPUT_CHARS"
              :label="tm('codingAgentsEditor.maxOutputChars')"
              density="compact"
              variant="outlined"
              hide-details
              @blur="
                commitNumber(
                  index,
                  'max_output_chars',
                  $event,
                  MIN_MAX_OUTPUT_CHARS,
                  DEFAULT_MAX_OUTPUT_CHARS,
                )
              "
            />
          </v-col>
        </v-row>

        <div class="coding-agents-editor__extra-args mt-2">
          <div class="text-subtitle-2">
            {{ tm('codingAgentsEditor.extraArgs') }}
          </div>
          <div class="text-body-2 text-medium-emphasis mb-1">
            {{ tm('codingAgentsEditor.extraArgsHint') }}
          </div>
          <ListConfigItem
            :model-value="entry.extra_args"
            :prefer-single-item="false"
            :max-display-items="2"
            :button-text="tm('codingAgentsEditor.addArgument')"
            :dialog-title="tm('codingAgentsEditor.extraArgs')"
            @update:model-value="
              patchAgent(index, { extra_args: textList($event) })
            "
          />
        </div>

        <div class="coding-agents-editor__env mt-2">
          <div class="text-subtitle-2">{{ tm('codingAgentsEditor.env') }}</div>
          <div class="text-body-2 text-medium-emphasis mb-1">
            {{ tm('codingAgentsEditor.envHint') }}
          </div>
          <ListConfigItem
            :model-value="envLines(entry)"
            :prefer-single-item="false"
            :max-display-items="2"
            :button-text="tm('codingAgentsEditor.addEnv')"
            :dialog-title="tm('codingAgentsEditor.env')"
            @update:model-value="
              patchAgent(index, { env: envFromLines($event) })
            "
          />
        </div>

        <div class="coding-agents-editor__providers mt-4">
          <div class="text-subtitle-1">
            {{ tm('codingAgentsEditor.providers') }}
          </div>
          <div class="text-body-2 text-medium-emphasis mb-2">
            {{
              entry.type === 'custom'
                ? tm('codingAgentsEditor.providersCustomHint')
                : tm('codingAgentsEditor.providersHint')
            }}
          </div>

          <div
            v-if="entry.providers.length"
            class="coding-agents-editor__active-provider mb-2"
          >
            <v-select
              :model-value="entry.active_provider"
              :items="entry.providers.map((provider) => provider.id)"
              :label="tm('codingAgentsEditor.activeProvider')"
              :hint="tm('codingAgentsEditor.activeProviderHint')"
              persistent-hint
              density="compact"
              variant="outlined"
              @update:model-value="
                patchAgent(index, { active_provider: text($event) })
              "
            />
          </div>

          <v-alert
            v-else
            class="coding-agents-editor__no-providers"
            density="compact"
            variant="tonal"
            type="info"
          >
            {{ tm('codingAgentsEditor.noProviders') }}
          </v-alert>

          <v-card
            v-for="(provider, providerIndex) in entry.providers"
            :key="providerIndex"
            class="coding-agents-editor__provider mb-2"
            variant="tonal"
          >
            <v-card-text>
              <v-row density="compact">
                <v-col cols="12" sm="6">
                  <v-text-field
                    class="coding-agents-editor__provider-id"
                    :model-value="provider.id"
                    :label="tm('codingAgentsEditor.providerId')"
                    density="compact"
                    variant="outlined"
                    hide-details
                    @update:model-value="
                      patchProvider(index, providerIndex, { id: text($event) })
                    "
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    class="coding-agents-editor__provider-name"
                    :model-value="provider.name"
                    :label="tm('codingAgentsEditor.providerName')"
                    :placeholder="provider.id"
                    density="compact"
                    variant="outlined"
                    hide-details
                    @update:model-value="
                      patchProvider(index, providerIndex, {
                        name: text($event),
                      })
                    "
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    class="coding-agents-editor__provider-base-url"
                    :model-value="provider.base_url"
                    :label="tm('codingAgentsEditor.providerBaseUrl')"
                    density="compact"
                    variant="outlined"
                    hide-details
                    @update:model-value="
                      patchProvider(index, providerIndex, {
                        base_url: text($event),
                      })
                    "
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    class="coding-agents-editor__provider-api-key"
                    :model-value="provider.api_key"
                    :type="
                      revealed.has(providerKey(index, providerIndex))
                        ? 'text'
                        : 'password'
                    "
                    :label="tm('codingAgentsEditor.providerApiKey')"
                    :hint="tm('codingAgentsEditor.providerApiKeyHint')"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                    :append-inner-icon="
                      revealed.has(providerKey(index, providerIndex))
                        ? 'mdi-eye-off-outline'
                        : 'mdi-eye-outline'
                    "
                    @click:append-inner="
                      toggleRevealed(providerKey(index, providerIndex))
                    "
                    @update:model-value="
                      patchProvider(index, providerIndex, {
                        api_key: text($event),
                      })
                    "
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field
                    class="coding-agents-editor__provider-model"
                    :model-value="provider.model"
                    :label="tm('codingAgentsEditor.providerModel')"
                    density="compact"
                    variant="outlined"
                    hide-details
                    @update:model-value="
                      patchProvider(index, providerIndex, {
                        model: text($event),
                      })
                    "
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <v-select
                    class="coding-agents-editor__provider-wire-api"
                    :model-value="provider.wire_api"
                    :items="wireApiOptions(provider.wire_api)"
                    :label="tm('codingAgentsEditor.providerWireApi')"
                    :hint="tm('codingAgentsEditor.providerWireApiHint')"
                    persistent-hint
                    density="compact"
                    variant="outlined"
                    @update:model-value="
                      patchProvider(index, providerIndex, {
                        wire_api: text($event),
                      })
                    "
                  />
                </v-col>
              </v-row>
              <div class="d-flex justify-end">
                <v-btn
                  class="coding-agents-editor__remove-provider"
                  color="error"
                  variant="text"
                  size="small"
                  prepend-icon="mdi-delete"
                  @click="removeProvider(index, providerIndex)"
                >
                  {{ tm('codingAgentsEditor.removeProvider') }}
                </v-btn>
              </div>
            </v-card-text>
          </v-card>

          <div class="d-flex justify-end">
            <v-btn
              class="coding-agents-editor__add-provider"
              color="primary"
              variant="tonal"
              size="small"
              prepend-icon="mdi-plus"
              @click="addProvider(index)"
            >
              {{ tm('codingAgentsEditor.addProvider') }}
            </v-btn>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import ListConfigItem from './ListConfigItem.vue';

type AgentType = 'claude_code' | 'codex' | 'custom';

interface ProviderPreset {
  id: string;
  name: string;
  base_url: string;
  api_key: string;
  model: string;
  wire_api: string;
}

interface CodingAgent {
  [key: string]: unknown;
  id: string;
  name: string;
  type: AgentType;
  enabled: boolean;
  command: string;
  model: string;
  permission_mode: string;
  sandbox: string;
  project_dir: string;
  extra_args: string[];
  env: Record<string, string>;
  timeout_seconds: number;
  max_output_chars: number;
  active_provider: string;
  providers: ProviderPreset[];
}

// Mirrors `astrbot/core/agent/btw/coding_agents.py`.
const CODING_AGENT_TYPES: AgentType[] = ['claude_code', 'codex', 'custom'];
const TYPE_OPTIONS = [...CODING_AGENT_TYPES];
const DEFAULT_COMMANDS: Record<AgentType, string> = {
  claude_code: 'claude',
  codex: 'codex',
  custom: '',
};
const CLAUDE_PERMISSION_MODES = [
  'acceptEdits',
  'auto',
  'bypassPermissions',
  'manual',
  'dontAsk',
  'plan',
];
const CODEX_SANDBOXES = ['read-only', 'workspace-write', 'danger-full-access'];
const WIRE_APIS = ['responses', 'chat'];
const DEFAULT_PERMISSION_MODE = 'acceptEdits';
const DEFAULT_SANDBOX = 'workspace-write';
const DEFAULT_TIMEOUT_SECONDS = 1800;
const DEFAULT_MAX_OUTPUT_CHARS = 20000;
const MIN_TIMEOUT_SECONDS = 1;
const MIN_MAX_OUTPUT_CHARS = 200;

const props = defineProps<{
  modelValue?: unknown;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: CodingAgent[]];
}>();

const { tm } = useModuleI18n('features/config');
const revealed = ref(new Set<string>());

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function enumOr(value: unknown, allowed: string[], fallback: string): string {
  const candidate = text(value).trim();
  return allowed.includes(candidate) ? candidate : fallback;
}

function textList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === 'string' && item !== '',
      )
    : [];
}

function envMap(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  const entries: [string, string][] = [];
  for (const [key, item] of Object.entries(value)) {
    if (key && typeof item === 'string') entries.push([key, item]);
  }
  return Object.fromEntries(entries);
}

function countOr(value: unknown, fallback: number, minimum: number): number {
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) && parsed >= minimum ? parsed : fallback;
}

function projectProvider(raw: unknown): ProviderPreset | null {
  if (!isRecord(raw)) return null;
  const id = text(raw.id).trim();
  if (!id) return null;
  const name = text(raw.name);
  return {
    ...raw,
    id,
    name: name || id,
    base_url: text(raw.base_url),
    api_key: text(raw.api_key),
    model: text(raw.model),
    wire_api: text(raw.wire_api).trim() || 'responses',
  };
}

function projectProviders(raw: unknown): ProviderPreset[] {
  const providers: ProviderPreset[] = [];
  const seen = new Set<string>();
  for (const item of Array.isArray(raw) ? raw : []) {
    const provider = projectProvider(item);
    if (provider && !seen.has(provider.id)) {
      seen.add(provider.id);
      providers.push(provider);
    }
  }
  return providers;
}

/**
 * Project one stored entry onto the shape the backend would actually use.
 *
 * The value comes from a profile, so a malformed field is shown as the default
 * the backend would substitute rather than as itself: the editor must not
 * display a value that would be discarded on the next run.
 */
function projectAgent(raw: unknown): CodingAgent | null {
  if (!isRecord(raw)) return null;
  const type = CODING_AGENT_TYPES.includes(raw.type as AgentType)
    ? (raw.type as AgentType)
    : 'claude_code';
  const providers = projectProviders(raw.providers);
  const providerIds = providers.map((provider) => provider.id);
  const active = text(raw.active_provider).trim();
  return {
    ...raw,
    id: text(raw.id).trim(),
    name: text(raw.name),
    type,
    enabled: raw.enabled === true,
    command: text(raw.command),
    model: text(raw.model),
    permission_mode: enumOr(
      raw.permission_mode,
      CLAUDE_PERMISSION_MODES,
      DEFAULT_PERMISSION_MODE,
    ),
    sandbox: enumOr(raw.sandbox, CODEX_SANDBOXES, DEFAULT_SANDBOX),
    project_dir: text(raw.project_dir),
    extra_args: textList(raw.extra_args),
    env: envMap(raw.env),
    timeout_seconds: countOr(
      raw.timeout_seconds || DEFAULT_TIMEOUT_SECONDS,
      DEFAULT_TIMEOUT_SECONDS,
      MIN_TIMEOUT_SECONDS,
    ),
    max_output_chars: countOr(
      raw.max_output_chars || DEFAULT_MAX_OUTPUT_CHARS,
      DEFAULT_MAX_OUTPUT_CHARS,
      MIN_MAX_OUTPUT_CHARS,
    ),
    active_provider: providerIds.includes(active)
      ? active
      : (providerIds[0] ?? ''),
    providers,
  };
}

const entries = computed<CodingAgent[]>(() =>
  Array.isArray(props.modelValue)
    ? props.modelValue
        .map(projectAgent)
        .filter((agent): agent is CodingAgent => agent !== null)
    : [],
);

function commit(next: CodingAgent[]) {
  emit('update:modelValue', next);
}

function patchAgent(index: number, patch: Partial<CodingAgent>) {
  commit(
    entries.value.map((entry, i) =>
      i === index ? { ...entry, ...patch } : entry,
    ),
  );
}

function patchProvider(
  agentIndex: number,
  providerIndex: number,
  patch: Partial<ProviderPreset>,
) {
  const agent = entries.value[agentIndex];
  const providers = agent.providers.map((provider, i) =>
    i === providerIndex ? { ...provider, ...patch } : provider,
  );
  patchAgent(agentIndex, {
    providers,
    active_provider: repointActive(providers, agent.active_provider),
  });
}

/** Keep `active_provider` naming a preset that still exists, as the backend does. */
function repointActive(providers: ProviderPreset[], current: string): string {
  const ids = providers.map((provider) => provider.id);
  return ids.includes(current) ? current : (ids[0] ?? '');
}

function uniqueId(existing: string[], base: string): string {
  if (!existing.includes(base)) return base;
  let suffix = 2;
  while (existing.includes(`${base}-${suffix}`)) suffix += 1;
  return `${base}-${suffix}`;
}

function newAgent(id: string): CodingAgent {
  return {
    id,
    name: '',
    type: 'claude_code',
    // A new entry must not run before it has been configured.
    enabled: false,
    command: DEFAULT_COMMANDS.claude_code,
    model: '',
    permission_mode: DEFAULT_PERMISSION_MODE,
    sandbox: DEFAULT_SANDBOX,
    project_dir: '',
    extra_args: [],
    env: {},
    timeout_seconds: DEFAULT_TIMEOUT_SECONDS,
    max_output_chars: DEFAULT_MAX_OUTPUT_CHARS,
    active_provider: '',
    providers: [],
  };
}

function addAgent() {
  const id = uniqueId(
    entries.value.map((entry) => entry.id),
    'agent',
  );
  commit([...entries.value, newAgent(id)]);
}

function removeAgent(index: number) {
  commit(entries.value.filter((_, i) => i !== index));
}

function moveAgent(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= entries.value.length) return;
  const next = [...entries.value];
  [next[index], next[target]] = [next[target], next[index]];
  commit(next);
}

/** Follow the type's default command, but never over a command someone typed. */
function setType(index: number, value: unknown) {
  const entry = entries.value[index];
  const type = CODING_AGENT_TYPES.includes(value as AgentType)
    ? (value as AgentType)
    : 'claude_code';
  const previousDefault = DEFAULT_COMMANDS[entry.type];
  const command =
    entry.command === '' || entry.command === previousDefault
      ? DEFAULT_COMMANDS[type]
      : entry.command;
  patchAgent(index, { type, command });
}

function addProvider(agentIndex: number) {
  const agent = entries.value[agentIndex];
  const id = uniqueId(
    agent.providers.map((provider) => provider.id),
    'provider',
  );
  patchAgent(agentIndex, {
    providers: [
      ...agent.providers,
      {
        id,
        name: id,
        base_url: '',
        api_key: '',
        model: '',
        wire_api: 'responses',
      },
    ],
    // A new preset becomes active only when nothing else is.
    active_provider: agent.active_provider || id,
  });
}

function removeProvider(agentIndex: number, providerIndex: number) {
  const agent = entries.value[agentIndex];
  const providers = agent.providers.filter((_, i) => i !== providerIndex);
  patchAgent(agentIndex, {
    providers,
    active_provider: repointActive(providers, agent.active_provider),
  });
}

/** Let a hand-written wire API stay selectable instead of blanking the field. */
function wireApiOptions(current: string): string[] {
  return WIRE_APIS.includes(current) ? [...WIRE_APIS] : [...WIRE_APIS, current];
}

function commitNumber(
  index: number,
  field: 'timeout_seconds' | 'max_output_chars',
  event: Event,
  minimum: number,
  fallback: number,
) {
  const raw = (event.target as HTMLInputElement | null)?.value ?? '';
  patchAgent(index, { [field]: countOr(raw, fallback, minimum) });
}

function providerKey(agentIndex: number, providerIndex: number): string {
  return `${agentIndex}:${providerIndex}`;
}

function toggleRevealed(key: string) {
  const next = new Set(revealed.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  revealed.value = next;
}

/** `env` is a map on disk; the list editor holds strings, so it spells them out. */
function envLines(entry: CodingAgent): string[] {
  return Object.entries(entry.env).map(([key, value]) => `${key}=${value}`);
}

function envFromLines(value: unknown): Record<string, string> {
  const env: Record<string, string> = {};
  for (const line of textList(value)) {
    const separator = line.indexOf('=');
    const key = (separator === -1 ? line : line.slice(0, separator)).trim();
    if (!key) continue;
    env[key] = separator === -1 ? '' : line.slice(separator + 1);
  }
  return env;
}

/**
 * What the backend would refuse, said where the operator can still fix it.
 *
 * Entries are never dropped here: `normalize_coding_agents` already ignores the
 * unusable ones, and removing text from under someone who is still typing is
 * worse than telling them it will be ignored.
 */
function warningsFor(index: number): string[] {
  const entry = entries.value[index];
  const warnings: string[] = [];
  const id = entry.id.trim();
  if (!id) warnings.push(tm('codingAgentsEditor.missingIdWarning'));
  else if (
    entries.value.slice(0, index).some((other) => other.id.trim() === id)
  ) {
    warnings.push(tm('codingAgentsEditor.duplicateIdWarning'));
  }
  if (entry.type === 'custom' && !entry.command.trim()) {
    warnings.push(tm('codingAgentsEditor.missingCommandWarning'));
  }
  if (!entry.enabled) warnings.push(tm('codingAgentsEditor.disabledWarning'));
  if (
    entry.type === 'claude_code' &&
    entry.permission_mode === 'bypassPermissions'
  ) {
    warnings.push(tm('codingAgentsEditor.riskyPermissionWarning'));
  }
  if (entry.type === 'codex' && entry.sandbox === 'danger-full-access') {
    warnings.push(tm('codingAgentsEditor.riskySandboxWarning'));
  }
  return warnings;
}
</script>

<style scoped>
.coding-agents-editor__provider {
  border-inline-start: 2px solid
    rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>

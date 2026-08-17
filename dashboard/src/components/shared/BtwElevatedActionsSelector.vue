<template>
  <div class="btw-elevated-actions-selector">
    <v-alert density="compact" variant="tonal" type="info" class="mb-3">
      {{ tm('btwElevatedActionsSelector.hint') }}
    </v-alert>
    <v-table density="compact">
      <thead>
        <tr>
          <th>{{ tm('btwElevatedActionsSelector.action') }}</th>
          <th>{{ tm('btwElevatedActionsSelector.workLoop') }}</th>
          <th>
            <v-icon size="small" icon="mdi-lock-outline" />
            <span class="ml-1">{{
              tm('btwElevatedActionsSelector.conversationLoop')
            }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="action in ACTIONS" :key="action.value">
          <td>
            <div>
              {{ tm(`btwElevatedActionsSelector.actions.${action.value}`) }}
            </div>
            <div class="text-medium-emphasis text-body-2">
              {{ action.value }}
            </div>
          </td>
          <td class="btw-elevated-actions-selector__control">
            <v-switch
              :model-value="isEnabled(action.value)"
              color="primary"
              density="compact"
              hide-details
              @update:model-value="setEnabled(action.value, $event)"
            />
          </td>
          <td class="btw-elevated-actions-selector__locked">
            <v-tooltip
              :text="tm('btwElevatedActionsSelector.conversationLocked')"
            >
              <template #activator="{ props: activatorProps }">
                <v-icon
                  v-bind="activatorProps"
                  size="small"
                  icon="mdi-lock-off-outline"
                />
              </template>
            </v-tooltip>
          </td>
        </tr>
      </tbody>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

// The six high-risk ``tool.*`` actions the BTW work loop may auto-elevate.
// Mirrors the backend default and ``HIGH_RISK_ACTIONS``; the conversation
// loop hard-disables all of these, so its column is read-only.
const ACTIONS = [
  { value: 'tool.local_exec' },
  { value: 'tool.python_exec' },
  { value: 'tool.file_write' },
  { value: 'tool.browser_control' },
  { value: 'tool.mcp_write' },
  { value: 'tool.computer_use' },
] as const;

const ALL_ACTIONS: string[] = ACTIONS.map((action) => action.value);

const props = defineProps<{
  modelValue?: unknown;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string[]];
}>();

const { tm } = useModuleI18n('features/config');

const enabledActions = computed<string[]>(() => {
  const value = props.modelValue;
  if (!Array.isArray(value)) return [...ALL_ACTIONS];
  const known = value.filter(
    (item): item is string =>
      typeof item === 'string' && ALL_ACTIONS.includes(item),
  );
  // An empty or fully-invalid list means "default = all on", matching the
  // backend default; never persist an empty selection as "none".
  return known.length ? known : [...ALL_ACTIONS];
});

function isEnabled(action: string): boolean {
  return enabledActions.value.includes(action);
}

function setEnabled(action: string, value: unknown) {
  const on = Boolean(value);
  const next = new Set(enabledActions.value);
  if (on) next.add(action);
  else next.delete(action);
  // Keep it from going empty while there is at least the option being
  // toggled off here — but an operator may legitimately disable all six; an
  // empty list is emitted as-is so the backend deny applies.  We only guard
  // the *default/unknown* case above, not an explicit all-off choice.
  emit(
    'update:modelValue',
    ALL_ACTIONS.filter((a) => next.has(a)),
  );
}
</script>

<style scoped>
.btw-elevated-actions-selector__control {
  width: 120px;
}
.btw-elevated-actions-selector__locked {
  width: 200px;
}
</style>

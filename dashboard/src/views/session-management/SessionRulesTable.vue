<template>
  <v-data-table-server
    v-model:items-per-page="tableItemsPerPage"
    :items-per-page-options="itemsPerPageOptions"
    v-model:page="tablePage"
    v-model="tableSelectedItems"
    :headers="headers"
    :items="items"
    :loading="loading"
    :items-length="itemsLength"
    class="elevation-0 session-rules-table"
    show-select
    :item-value="itemValue"
    return-object
    @update:options="emit('update:options', $event)"
  >
    <!-- UMO 信息 -->
    <template #item.umo_info="{ item }">
      <span class="mobile-field-label">{{ headers[0]?.title }}</span>
      <code v-if="isSenderRule(item)" class="text-body-2">{{
        item.sender_id
      }}</code>
      <UmoDisplay
        v-else
        :umo="item.umo"
        :platform="item.platform"
        :message-type="item.message_type"
        :session-id="item.session_id"
        :auto-name="item.auto_name"
        :user-alias="item.user_alias"
        :custom-name="item.rules?.session_service_config?.custom_name"
        editable
        :edit-tooltip="tm('buttons.editCustomName')"
        @edit="emit('edit-custom-name', item)"
      />
    </template>

    <!-- 规则概览 -->
    <template #item.rules_overview="{ item }">
      <span class="mobile-field-label">{{ headers[1]?.title }}</span>
      <div v-if="isSenderRule(item)" class="d-flex flex-wrap ga-1">
        <v-chip
          v-if="item.rules.session_service_config?.blocked === true"
          size="x-small"
          color="error"
          variant="outlined"
        >
          {{ tm('customRules.blocked') }}
        </v-chip>
        <v-chip
          v-if="
            typeof item.rules.session_service_config?.llm_enabled === 'boolean'
          "
          size="x-small"
          color="primary"
          variant="outlined"
        >
          {{ tm('customRules.llmEnabled') }}
        </v-chip>
      </div>
      <div v-else class="d-flex flex-wrap ga-1">
        <v-chip
          v-if="item.rules.session_service_config"
          size="x-small"
          color="primary"
          variant="outlined"
        >
          {{ tm('customRules.serviceConfig') }}
        </v-chip>
        <v-chip
          v-if="item.rules.session_plugin_config"
          size="x-small"
          color="secondary"
          variant="outlined"
        >
          {{ tm('customRules.pluginConfig') }}
        </v-chip>
        <v-chip
          v-if="item.rules.kb_config"
          size="x-small"
          color="info"
          variant="outlined"
        >
          {{ tm('customRules.kbConfig') }}
        </v-chip>
        <v-chip
          v-if="hasProviderConfig(item.rules)"
          size="x-small"
          color="warning"
          variant="outlined"
        >
          {{ tm('customRules.providerConfig') }}
        </v-chip>
      </div>
    </template>

    <!-- 操作按钮 -->
    <template #item.actions="{ item }">
      <span class="mobile-field-label">{{ headers[2]?.title }}</span>
      <div class="session-rule-actions">
        <v-btn
          size="small"
          variant="tonal"
          color="primary"
          class="mr-1"
          :aria-label="tm('buttons.editRule')"
          @click="emit('edit-rule', item)"
        >
          <v-icon>mdi-pencil</v-icon>
          <v-tooltip activator="parent" location="top">{{
            tm('buttons.editRule')
          }}</v-tooltip>
        </v-btn>
        <v-btn
          size="small"
          variant="tonal"
          color="error"
          :aria-label="tm('buttons.deleteAllRules')"
          @click="emit('delete-rules', item)"
        >
          <v-icon>mdi-delete</v-icon>
          <v-tooltip activator="parent" location="top">{{
            tm('buttons.deleteAllRules')
          }}</v-tooltip>
        </v-btn>
      </div>
    </template>

    <!-- 空状态 -->
    <template #no-data>
      <div class="text-center py-8">
        <v-icon size="64" color="on-surface-variant"
          >mdi-file-document-edit-outline</v-icon
        >
        <div class="text-title-small mt-4">
          {{ tm('customRules.noRules') }}
        </div>
        <div class="text-body-2 text-medium-emphasis">
          {{
            isSenderTarget
              ? tm('customRules.noSenderRulesDesc')
              : tm('customRules.noRulesDesc')
          }}
        </div>
        <v-btn
          color="primary"
          variant="tonal"
          class="mt-4"
          @click="emit('add-rule')"
        >
          <v-icon start>mdi-plus</v-icon>
          {{ tm('buttons.addRule') }}
        </v-btn>
      </div>
    </template>
  </v-data-table-server>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import UmoDisplay from '@/components/shared/UmoDisplay.vue';
import { useModuleI18n } from '@/i18n/composables';
import { hasProviderConfig, isSenderRule } from './sessionRuleNormalizers';
import type {
  SessionRuleItem,
  SessionTableHeader,
  TableOptionsLike,
} from './sessionRuleHelpers';

const props = defineProps<{
  headers: SessionTableHeader[];
  items: SessionRuleItem[];
  loading: boolean;
  itemsLength: number;
  itemsPerPage: number;
  page: number;
  selectedItems: SessionRuleItem[];
  itemValue: string;
  isSenderTarget: boolean;
  itemsPerPageOptions?: number[];
}>();

const emit = defineEmits<{
  'update:itemsPerPage': [value: number];
  'update:page': [value: number];
  'update:selectedItems': [value: SessionRuleItem[]];
  'update:options': [options: TableOptionsLike];
  'edit-rule': [item: SessionRuleItem];
  'delete-rules': [item: SessionRuleItem];
  'edit-custom-name': [item: SessionRuleItem];
  'add-rule': [];
}>();

const { tm } = useModuleI18n('features/session-management');

const tableItemsPerPage = computed({
  get: () => props.itemsPerPage,
  set: (value: number) => {
    emit('update:itemsPerPage', value);
  },
});

const tablePage = computed({
  get: () => props.page,
  set: (value: number) => {
    emit('update:page', value);
  },
});

const tableSelectedItems = computed({
  get: () => props.selectedItems,
  set: (value: SessionRuleItem[]) => {
    emit('update:selectedItems', value);
  },
});
</script>

<style scoped>
.session-rules-table {
  font-size: 12px;
}

.mobile-field-label {
  display: none;
}

.session-rule-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: var(--astrbot-space-2);
}

code {
  background-color: rgb(var(--v-theme-surface-variant));
  padding: 2px var(--astrbot-space-2);
  border-radius: 4px;
  font-size: 12px;
}

@media (max-width: 600px) {
  .session-rules-table :deep(.v-table__wrapper) {
    overflow-x: visible;
  }

  .session-rules-table :deep(table),
  .session-rules-table :deep(tbody) {
    display: block;
    min-width: 0;
    width: 100%;
  }

  .session-rules-table :deep(thead) {
    display: none;
  }

  .session-rules-table :deep(tbody) {
    display: grid;
    gap: var(--astrbot-space-2);
    padding: var(--astrbot-space-3);
  }

  .session-rules-table :deep(tbody tr) {
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgb(var(--v-theme-outline-variant));
    border-radius: 8px;
    display: grid;
    gap: var(--astrbot-space-2) var(--astrbot-space-3);
    grid-template-areas:
      'select subject'
      'rules rules'
      'actions actions';
    grid-template-columns: 32px minmax(0, 1fr);
    padding: var(--astrbot-space-3);
  }

  .session-rules-table :deep(tbody td) {
    border-bottom: 0;
    height: auto;
    min-width: 0;
    padding: 0;
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .session-rules-table :deep(tbody td:nth-child(1)) {
    align-self: start;
    grid-area: select;
    width: auto !important;
  }

  .session-rules-table :deep(tbody td:nth-child(2)) {
    grid-area: subject;
  }

  .session-rules-table :deep(tbody td:nth-child(3)) {
    grid-area: rules;
  }

  .session-rules-table :deep(tbody td:nth-child(4)) {
    grid-area: actions;
  }

  .session-rules-table :deep(.mobile-field-label) {
    color: rgb(var(--v-theme-on-surface-variant));
    display: block;
    font-size: var(--astrbot-meta-size);
    line-height: 1.5;
    margin-bottom: 4px;
  }

  .session-rules-table :deep(.umo-display__name),
  .session-rules-table :deep(.umo-display__umo) {
    overflow: visible;
    text-overflow: clip;
    white-space: normal;
  }

  .session-rules-table :deep(.umo-display) {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .session-rules-table :deep(.umo-display__actions) {
    justify-content: flex-end;
    width: 100%;
  }
}
</style>

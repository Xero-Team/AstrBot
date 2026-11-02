<template>
  <div class="settings-page">
    <header class="settings-page__header">
      <h1 class="page-header__title">{{ tm('page.title') }}</h1>
    </header>

    <div class="settings-layout">
      <nav class="settings-nav" :aria-label="tm('page.title')">
        <button
          v-for="item in settingsNavItems"
          :key="item.id"
          type="button"
          class="settings-nav__item"
          :class="{
            'settings-nav__item--active': activeSettingsSection === item.id,
          }"
          :aria-pressed="activeSettingsSection === item.id"
          @click="activeSettingsSection = item.id"
        >
          <span
            class="settings-nav__icon"
            :class="item.icon"
            aria-hidden="true"
          ></span>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <main class="settings-main">
        <v-slide-y-reverse-transition>
          <div
            v-if="systemConfigRestartRequired"
            class="system-config-restart-bar"
            role="status"
          >
            <div class="system-config-restart-bar__inner">
              <div class="system-config-restart-bar__message">
                <v-icon size="18">mdi-alert-circle</v-icon>
                <span>{{ tm('systemConfig.restartRequired') }}</span>
              </div>
              <v-btn
                size="small"
                variant="tonal"
                class="system-config-restart-bar__button"
                @click="restartAstrBot"
              >
                <v-icon class="mr-1" size="17">mdi-restart</v-icon>
                {{ tm('system.restart.button') }}
              </v-btn>
            </div>
          </div>
        </v-slide-y-reverse-transition>

        <v-progress-linear
          v-if="systemConfigLoading || systemConfigSaving"
          indeterminate
          color="primary"
          class="mb-4"
        />

        <section
          v-show="activeSettingsSection === 'general'"
          id="system-config"
          class="settings-section"
        >
          <div class="settings-section__heading">
            <div class="settings-section__title">
              {{ tm('sections.general.title') }}
            </div>
          </div>
          <div class="settings-section__content">
            <template v-if="!systemConfigLoading">
              <div
                v-for="group in generalSystemConfigGroups"
                :key="group.key"
                class="system-config-group"
                :class="{
                  'system-config-group--with-cleanup':
                    group.key === 'tempStorage',
                }"
                @focusout.capture="scheduleSystemConfigAutoSave"
              >
                <div class="system-config-group__heading">
                  <div class="system-config-group__title">
                    {{ group.title }}
                  </div>
                  <div
                    v-if="group.key === 'runtime' && timezoneTimePreview"
                    class="timezone-time-preview"
                  >
                    <span class="timezone-time-preview__item">
                      {{ tm('systemConfig.timePreview.label') }} ·
                      {{ timezoneTimePreview.offsetLabel }}
                      {{ timezoneTimePreview.localTime }}
                    </span>
                  </div>
                </div>
                <AstrBotConfigV4
                  :metadata="group.metadata"
                  :iterable="systemConfigData"
                  :metadata-key="group.key"
                />
                <StorageCleanupPanel
                  v-if="group.key === 'tempStorage'"
                  class="storage-cleanup-panel--attached"
                />
              </div>
            </template>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'appearance'"
          id="settings-appearance"
          class="settings-section"
        >
          <div class="settings-section__heading">
            <div class="settings-section__title">
              {{ tm('sections.appearance.title') }}
            </div>
          </div>
          <div class="settings-section__content">
            <div class="settings-list-card">
              <div class="settings-item">
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    {{ tm('sidebar.customize.title') }}
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('sidebar.customize.subtitle') }}
                  </div>
                </div>
                <div class="settings-item__control">
                  <SidebarCustomizer />
                </div>
              </div>

              <div class="settings-item settings-item--color">
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    {{ tm('theme.customize.title') }}
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('theme.subtitle') }}
                  </div>
                </div>
                <div
                  class="settings-item__control settings-item__control--wide"
                >
                  <div class="color-controls">
                    <v-text-field
                      v-model="primaryColor"
                      type="color"
                      :label="tm('theme.customize.primary')"
                      hide-details
                      variant="outlined"
                      density="compact"
                    />
                    <v-text-field
                      v-model="secondaryColor"
                      type="color"
                      :label="tm('theme.customize.secondary')"
                      hide-details
                      variant="outlined"
                      density="compact"
                    />
                    <v-btn
                      size="small"
                      variant="tonal"
                      color="primary"
                      @click="resetThemeColors"
                    >
                      <v-icon class="mr-2">mdi-restore</v-icon>
                      {{ tm('theme.customize.reset') }}
                    </v-btn>
                  </div>
                </div>
              </div>
            </div>

            <DashboardAppearanceSettings />

            <template v-if="!systemConfigLoading">
              <div
                v-for="group in appearanceSystemConfigGroups"
                :key="group.key"
                class="system-config-group"
                @focusout.capture="scheduleSystemConfigAutoSave"
              >
                <div class="system-config-group__title">{{ group.title }}</div>
                <AstrBotConfigV4
                  :metadata="group.metadata"
                  :iterable="systemConfigData"
                  :metadata-key="group.key"
                />
              </div>
            </template>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'network'"
          id="settings-network"
          class="settings-section"
        >
          <div class="settings-section__heading">
            <div class="settings-section__title">
              {{ tm('sections.network.title') }}
            </div>
          </div>
          <div class="settings-section__content">
            <template v-if="!systemConfigLoading">
              <div
                v-for="group in networkSystemConfigGroups"
                :key="group.key"
                class="system-config-group"
                @focusout.capture="scheduleSystemConfigAutoSave"
              >
                <div class="system-config-group__title">{{ group.title }}</div>
                <AstrBotConfigV4
                  :metadata="group.metadata"
                  :iterable="systemConfigData"
                  :metadata-key="group.key"
                />
              </div>
            </template>

            <div class="settings-list-card">
              <div
                class="settings-item settings-item--stack settings-item--proxy"
              >
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    {{ tm('network.pypiMirror.title') }}
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('network.pypiMirror.subtitle') }}
                  </div>
                </div>
                <div
                  class="settings-item__control settings-item__control--proxy"
                >
                  <PypiMirrorSelector
                    :model-value="String(systemConfigData.pypi_index_url ?? '')"
                    @update:model-value="
                      systemConfigData.pypi_index_url = $event
                    "
                  />
                </div>
              </div>
            </div>

            <div class="settings-list-card">
              <div
                class="settings-item settings-item--stack settings-item--proxy"
              >
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    {{ tm('network.githubProxy.title') }}
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('network.githubProxy.subtitle') }}
                  </div>
                </div>
                <div
                  class="settings-item__control settings-item__control--proxy"
                >
                  <ProxySelector />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'security'"
          id="settings-security"
          class="settings-section"
        >
          <div class="settings-section__heading">
            <div class="settings-section__title">
              {{ tm('sections.security.title') }}
              <ConfigDocsLink docs="use/webui.html" />
            </div>
          </div>
          <div class="settings-section__content">
            <template v-if="!systemConfigLoading">
              <div
                v-for="group in securitySystemConfigGroups"
                :key="group.key"
                class="system-config-group"
                @focusout.capture="scheduleSystemConfigAutoSave"
              >
                <div class="system-config-group__title">{{ group.title }}</div>
                <AstrBotConfigV4
                  :metadata="group.metadata"
                  :iterable="systemConfigData"
                  :metadata-key="group.key"
                />
              </div>
            </template>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'maintenance'"
          id="settings-maintenance"
          class="settings-section"
        >
          <div class="settings-section__heading">
            <div class="settings-section__title">
              {{ tm('sections.maintenance.title') }}
            </div>
          </div>
          <div class="settings-section__content">
            <div class="settings-list-card">
              <div class="settings-item">
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    {{ tm('system.backup.title') }}
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('system.backup.subtitle') }}
                  </div>
                </div>
                <div class="settings-item__control">
                  <v-btn
                    color="primary"
                    variant="tonal"
                    @click="openBackupDialog"
                  >
                    <v-icon class="mr-2">mdi-backup-restore</v-icon>
                    {{ tm('system.backup.button') }}
                  </v-btn>
                </div>
              </div>

              <div class="settings-item">
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    {{ tm('system.diagnostics.title') }}
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('system.diagnostics.subtitle') }}
                  </div>
                </div>
                <div class="settings-item__control">
                  <LogExportButton />
                </div>
              </div>

              <div class="settings-item">
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    {{ tm('system.restart.title') }}
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('system.restart.subtitle') }}
                  </div>
                </div>
                <div class="settings-item__control">
                  <v-btn color="error" variant="tonal" @click="restartAstrBot">
                    <v-icon class="mr-2">mdi-restart</v-icon>
                    {{ tm('system.restart.button') }}
                  </v-btn>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section
          v-show="activeSettingsSection === 'openapi'"
          id="settings-openapi"
          class="settings-section"
        >
          <div class="settings-section__heading">
            <div class="settings-section__title">
              {{ tm('sections.openapi.title') }}
            </div>
          </div>
          <div class="settings-section__content">
            <div class="settings-list-card">
              <div class="settings-item settings-item--stack">
                <div class="settings-item__label">
                  <div class="settings-item__title">
                    <span>{{ tm('apiKey.manageTitle') }}</span>
                    <v-tooltip location="top">
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          icon
                          size="x-small"
                          variant="text"
                          class="ml-2"
                          :aria-label="tm('apiKey.docsLink')"
                          :href="docsHref('dev/openapi.html')"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <v-icon size="18">mdi-help-circle-outline</v-icon>
                        </v-btn>
                      </template>
                      <span>{{ tm('apiKey.docsLink') }}</span>
                    </v-tooltip>
                  </div>
                  <div class="settings-item__subtitle">
                    {{ tm('apiKey.subtitle') }}
                  </div>
                </div>

                <div class="api-key-panel">
                  <div class="api-key-create-row">
                    <v-text-field
                      v-model="newApiKeyName"
                      :label="tm('apiKey.name')"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                    <v-select
                      v-model="newApiKeyExpiresInDays"
                      :items="apiKeyExpiryOptions"
                      :label="tm('apiKey.expiresInDays')"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                    <v-btn
                      color="primary"
                      variant="tonal"
                      :loading="apiKeyCreating"
                      @click="createApiKey"
                    >
                      <v-icon class="mr-2">mdi-key-plus</v-icon>
                      {{ tm('apiKey.create') }}
                    </v-btn>
                  </div>

                  <v-alert
                    v-if="newApiKeyExpiresInDays === 'permanent'"
                    type="warning"
                    variant="tonal"
                    density="comfortable"
                    class="my-3"
                  >
                    {{ tm('apiKey.permanentWarning') }}
                  </v-alert>

                  <div class="text-caption text-medium-emphasis mb-1">
                    {{ tm('apiKey.scopes') }}
                  </div>
                  <v-chip-group v-model="newApiKeyScopes" multiple class="mb-3">
                    <v-chip
                      v-for="scope in availableScopes"
                      :key="scope.value"
                      :value="scope.value"
                      :color="
                        newApiKeyScopes.includes(scope.value)
                          ? 'primary'
                          : undefined
                      "
                      :variant="
                        newApiKeyScopes.includes(scope.value) ? 'flat' : 'tonal'
                      "
                    >
                      {{ scope.label }}
                    </v-chip>
                  </v-chip-group>

                  <v-alert
                    v-if="createdApiKeyPlaintext"
                    type="warning"
                    variant="tonal"
                    class="mb-4"
                  >
                    <div
                      class="d-flex align-center justify-space-between flex-wrap"
                    >
                      <span>{{ tm('apiKey.plaintextHint') }}</span>
                      <v-btn
                        size="small"
                        variant="text"
                        color="primary"
                        @click="copyCreatedApiKey"
                      >
                        <v-icon class="mr-1">mdi-content-copy</v-icon
                        >{{ tm('apiKey.copy') }}
                      </v-btn>
                    </div>
                    <code class="api-key-plain">{{
                      createdApiKeyPlaintext
                    }}</code>
                  </v-alert>

                  <div class="settings-table-wrap">
                    <v-table density="compact">
                      <thead>
                        <tr>
                          <th>{{ tm('apiKey.table.name') }}</th>
                          <th>{{ tm('apiKey.table.scopes') }}</th>
                          <th>{{ tm('apiKey.table.status') }}</th>
                          <th>{{ tm('apiKey.table.lastUsed') }}</th>
                          <th>{{ tm('apiKey.table.createdAt') }}</th>
                          <th>{{ tm('apiKey.table.actions') }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="item in apiKeys" :key="item.key_id">
                          <td>
                            <div class="api-key-name-cell">
                              <div>{{ item.name }}</div>
                              <code>{{ item.key_prefix }}</code>
                            </div>
                          </td>
                          <td>{{ (item.scopes || []).join(', ') }}</td>
                          <td>
                            <v-chip
                              size="small"
                              :color="
                                item.is_revoked || item.is_expired
                                  ? 'error'
                                  : 'success'
                              "
                              variant="tonal"
                            >
                              {{
                                item.is_revoked || item.is_expired
                                  ? tm('apiKey.status.inactive')
                                  : tm('apiKey.status.active')
                              }}
                            </v-chip>
                          </td>
                          <td>{{ formatDate(item.last_used_at) }}</td>
                          <td>{{ formatDate(item.created_at) }}</td>
                          <td>
                            <div class="api-key-actions">
                              <v-btn
                                v-if="!item.is_revoked"
                                size="x-small"
                                color="warning"
                                variant="tonal"
                                @click="revokeApiKey(item.key_id)"
                              >
                                {{ tm('apiKey.revoke') }}
                              </v-btn>
                              <v-btn
                                size="x-small"
                                color="error"
                                variant="tonal"
                                @click="deleteApiKey(item.key_id)"
                              >
                                {{ tm('apiKey.delete') }}
                              </v-btn>
                            </div>
                          </td>
                        </tr>
                        <tr v-if="apiKeys.length === 0">
                          <td
                            colspan="6"
                            class="text-center text-medium-emphasis"
                          >
                            {{ tm('apiKey.empty') }}
                          </td>
                        </tr>
                      </tbody>
                    </v-table>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>

  <WaitingForRestart ref="wfr" />
  <BackupDialog ref="backupDialog" />
  <DashboardTwoFactorDialog
    v-model="configSave2faDialogVisible"
    :error-message="configSave2faError"
    :saving="configSave2faSaving"
    :rotation-hint="configSave2faRotationHint"
    @confirm="handleConfigSave2faConfirm"
    @cancel="handleConfigSave2faCancel"
  />
  <DashboardStepUpDialog
    v-model="stepUpDialogOpen"
    :loading="stepUpLoading"
    :error-message="stepUpErrorMessage"
    @confirm="submitStepUp"
    @cancel="cancelStepUp"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { apiKeyApi, systemConfigApi } from '@/api/v1';
import ConfigDocsLink from '@/components/shared/ConfigDocsLink.vue';
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ProxySelector from '@/components/shared/ProxySelector.vue';
import PypiMirrorSelector from '@/components/shared/PypiMirrorSelector.vue';
import SidebarCustomizer from '@/components/shared/SidebarCustomizer.vue';
import DashboardAppearanceSettings from '@/components/appearance/DashboardAppearanceSettings.vue';
import BackupDialog from '@/components/shared/BackupDialog.vue';
import StorageCleanupPanel from '@/components/shared/StorageCleanupPanel.vue';
import LogExportButton from '@/components/shared/LogExportButton.vue';
import DashboardTwoFactorDialog from '@/components/shared/DashboardTwoFactorDialog.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { runConfigMutationWithStepUp, stepUpHeaders } from '@/utils/stepUp';
import { restartAstrBot as restartAstrBotRuntime } from '@/utils/restartAstrBot';
import { copyToClipboard } from '@/utils/clipboard';
import { useModuleI18n } from '@/i18n/composables';
import { docsHref } from '@/utils/docsHref';
import { useTheme } from 'vuetify';
import { applyUserThemeColors, defaultThemeColors } from '@/design/theme';
import { useToastStore, type ToastColor } from '@/stores/toast';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';

type ApiKeyScope =
  | 'bot'
  | 'provider'
  | 'prompt'
  | 'im'
  | 'config'
  | 'chat'
  | 'kb'
  | 'memory'
  | 'data'
  | 'file'
  | 'plugin'
  | 'mcp'
  | 'skill';

type ApiKeyExpiry = number | 'permanent';

interface ApiKey {
  key_id: string;
  name?: string;
  key_prefix?: string;
  scopes?: string[];
  is_revoked?: boolean;
  is_expired?: boolean;
  last_used_at?: string | null;
  created_at?: string | null;
  [key: string]: unknown;
}

interface BackupDialogRef {
  open: () => void;
}

interface SystemConfigTemplateItemMeta {
  type?: string;
  default?: unknown;
  invisible?: boolean;
  description?: string;
  hint?: string;
  condition?: Record<string, unknown>;
  items: Record<string, SystemConfigTemplateItemMeta>;
  [key: string]: unknown;
}

interface SystemConfigTemplateMeta {
  name?: string;
  hint?: string;
  description?: string;
  hide_hint_in_list?: boolean;
  display_item?: string;
  items: Record<string, SystemConfigTemplateItemMeta>;
  [key: string]: unknown;
}

interface SystemConfigItemMeta {
  type?: string;
  description?: string;
  hint?: string;
  docs?: unknown;
  obvious_hint?: boolean;
  collapsed?: boolean;
  invisible?: boolean;
  full_width?: boolean;
  condition?: Record<string, unknown>;
  templates?: Record<string, SystemConfigTemplateMeta>;
  _special?: string;
  editor_mode?: boolean;
  editor_theme?: string;
  editor_language?: string;
  [key: string]: unknown;
}

interface SystemConfigGroupMeta {
  type?: string;
  description?: string;
  hint?: string;
  docs?: unknown;
  obvious_hint?: boolean;
  condition?: Record<string, unknown>;
  items?: Record<string, SystemConfigItemMeta>;
  [key: string]: unknown;
}

interface SystemConfigGroup {
  key: string;
  title: string;
  metadata: Record<string, SystemConfigGroupMeta>;
}

interface SystemConfigMetadata {
  system_group?: {
    metadata?: {
      system?: {
        items?: Record<string, SystemConfigItemMeta>;
      };
      [key: string]: unknown;
    };
  };
  [key: string]: unknown;
}

interface SystemConfigResponseData {
  config?: Record<string, unknown>;
  metadata?: SystemConfigMetadata;
  server_utc_time?: string;
  server_utc_offset_minutes?: number;
  server_timezone?: string;
  [key: string]: unknown;
}

interface ApiKeyCreatePayload {
  name: string;
  scopes: ApiKeyScope[];
  expires_in_days?: number;
}

const { tm } = useModuleI18n('features/settings');
const { tm: tmMeta } = useModuleI18n('features/config-metadata');
const toastStore = useToastStore();
const confirmDialog = useConfirmDialog();
const theme = useTheme();
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const getStoredColor = (key: string, fallback: string): string => {
  const stored =
    typeof window !== 'undefined' ? localStorage.getItem(key) : null;
  return stored || fallback;
};

const primaryColor = ref(
  getStoredColor('themePrimary', defaultThemeColors.primary),
);
const secondaryColor = ref(
  getStoredColor('themeSecondary', defaultThemeColors.secondary),
);

const resolveThemes = () => theme.themes.value ?? undefined;

const applyThemeColors = (primary: string | null, secondary: string | null) =>
  void applyUserThemeColors(resolveThemes(), primary, secondary);

applyThemeColors(primaryColor.value, secondaryColor.value);

watch(primaryColor, (value) => {
  if (!value) return;
  localStorage.setItem('themePrimary', value);
  applyThemeColors(value, secondaryColor.value);
});

watch(secondaryColor, (value) => {
  if (!value) return;
  localStorage.setItem('themeSecondary', value);
  applyThemeColors(primaryColor.value, value);
});

const wfr = ref(null);
const backupDialog = ref<BackupDialogRef | null>(null);
const apiKeys = ref<ApiKey[]>([]);
const apiKeyCreating = ref(false);
const newApiKeyName = ref('');
const newApiKeyExpiresInDays = ref<ApiKeyExpiry>(30);
const newApiKeyScopes = ref<ApiKeyScope[]>([
  'bot',
  'provider',
  'im',
  'config',
  'chat',
  'file',
]);
const createdApiKeyPlaintext = ref('');
const systemConfigData = ref<Record<string, unknown>>({});
const systemConfigMetadata = ref<SystemConfigMetadata>({});
const systemConfigLoading = ref(false);
const systemConfigSaving = ref(false);
const systemConfigLastSavedSnapshot = ref('{}');
const systemConfigRestartRequired = ref(false);
const configSave2faDialogVisible = ref(false);
const configSave2faError = ref('');
const configSave2faSaving = ref(false);
const configSave2faRotationHint = ref('');
const configSavePendingData = ref<Record<string, unknown> | null>(null);
const configSavePendingHeaders = ref<Record<string, string>>({});
const systemConfigAutoSaveTimer = ref<number | null>(null);
const serverUtcEpochMs = ref<number | null>(null);
const serverUtcOffsetMinutes = ref<number | null>(null);
const serverTimezone = ref<string | null>(null);
const serverClockAnchorMs = ref<number | null>(null);
const serverClockTickMs = ref<number | null>(null);
const serverClockTimer = ref<number | null>(null);
const activeSettingsSection = ref('general');

const apiKeyExpiryOptions = computed(() => [
  { title: tm('apiKey.expiryOptions.day1'), value: 1 },
  { title: tm('apiKey.expiryOptions.day7'), value: 7 },
  { title: tm('apiKey.expiryOptions.day30'), value: 30 },
  { title: tm('apiKey.expiryOptions.day90'), value: 90 },
  { title: tm('apiKey.expiryOptions.permanent'), value: 'permanent' },
]);

const availableScopes: { value: ApiKeyScope; label: string }[] = [
  { value: 'bot', label: 'bot' },
  { value: 'provider', label: 'provider' },
  { value: 'prompt', label: 'prompt' },
  { value: 'im', label: 'im' },
  { value: 'config', label: 'config' },
  { value: 'chat', label: 'chat' },
  { value: 'kb', label: 'kb' },
  { value: 'memory', label: 'memory' },
  { value: 'data', label: 'data' },
  { value: 'file', label: 'file' },
  { value: 'plugin', label: 'plugin' },
  { value: 'mcp', label: 'mcp' },
  { value: 'skill', label: 'skill' },
];

const settingsNavItems = computed(() => [
  {
    id: 'general',
    label: tm('sections.general.title'),
    icon: 'mdi mdi-tune-variant',
  },
  {
    id: 'appearance',
    label: tm('sections.appearance.title'),
    icon: 'mdi mdi-palette-outline',
  },
  {
    id: 'network',
    label: tm('sections.network.title'),
    icon: 'mdi mdi-lan-connect',
  },
  {
    id: 'security',
    label: tm('sections.security.title'),
    icon: 'mdi mdi-shield-lock-outline',
  },
  {
    id: 'maintenance',
    label: tm('sections.maintenance.title'),
    icon: 'mdi mdi-tools',
  },
  { id: 'openapi', label: tm('sections.openapi.title'), icon: 'mdi mdi-api' },
]);

const configIncludedScopes: ApiKeyScope[] = ['bot', 'provider'];
const previousApiKeyScopes = ref<ApiKeyScope[]>([...newApiKeyScopes.value]);

const systemConfigHasChanges = computed(
  () =>
    JSON.stringify(systemConfigData.value || {}) !==
    systemConfigLastSavedSnapshot.value,
);

const timezoneTimePreview = computed(() => {
  if (
    serverUtcEpochMs.value === null ||
    serverUtcOffsetMinutes.value === null ||
    serverClockAnchorMs.value === null ||
    serverClockTickMs.value === null
  ) {
    return null;
  }

  const elapsedMs = Math.max(
    0,
    serverClockTickMs.value - serverClockAnchorMs.value,
  );
  const instant = new Date(serverUtcEpochMs.value + elapsedMs);
  let localTime: string | null = null;
  try {
    if (serverTimezone.value) {
      const parts = new Intl.DateTimeFormat('en', {
        timeZone: serverTimezone.value,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
        .formatToParts(instant)
        .reduce<Record<string, string>>((result, part) => {
          result[part.type] = part.value;
          return result;
        }, {});
      localTime = `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
    }
  } catch {
    localTime = null;
  }

  if (!localTime) {
    const localDate = new Date(
      instant.getTime() + serverUtcOffsetMinutes.value * 60_000,
    );
    const localIsoTime = localDate.toISOString();
    localTime = `${localIsoTime.slice(0, 4)}/${localIsoTime.slice(5, 7)}/${localIsoTime.slice(8, 10)} ${localIsoTime.slice(11, 16)}`;
  }

  const absoluteOffset = Math.abs(serverUtcOffsetMinutes.value);
  const offsetHours = Math.floor(absoluteOffset / 60);
  const offsetMinutes = absoluteOffset % 60;
  const sign = serverUtcOffsetMinutes.value > 0 ? '+' : '-';
  const minutesPart = offsetMinutes
    ? `:${String(offsetMinutes).padStart(2, '0')}`
    : '';
  const offsetLabel =
    serverUtcOffsetMinutes.value === 0
      ? 'UTC'
      : `UTC${sign}${offsetHours}${minutesPart}`;

  return { localTime, offsetLabel };
});

const systemConfigGroups = computed<SystemConfigGroup[]>(() => {
  const systemSection =
    systemConfigMetadata.value?.system_group?.metadata?.system || {};
  const systemItems = systemSection.items || {};
  const createGroup = (key: string, itemKeys: string[]): SystemConfigGroup => {
    const items: Record<string, SystemConfigItemMeta> = {};
    itemKeys.forEach((itemKey) => {
      if (systemItems[itemKey]) {
        items[itemKey] = systemItems[itemKey];
      }
    });
    return {
      key,
      title: tm(`systemConfig.groups.${key}.title`),
      metadata: {
        [key]: {
          type: 'object',
          description: tm(`systemConfig.groups.${key}.title`),
          hint: '',
          items,
        },
      },
    };
  };

  return [
    createGroup('runtime', ['timezone', 'callback_api_base']),
    createGroup('network', ['http_proxy', 'no_proxy', 'pip_install_arg']),
    createGroup('webuiSecurity', [
      'dashboard.trust_proxy_headers',
      'dashboard.ssl.enable',
      'dashboard.ssl.cert_file',
      'dashboard.ssl.key_file',
      'dashboard.ssl.ca_certs',
      'dashboard.auth_rate_limit.enable',
      'dashboard.auth_rate_limit.average_interval',
      'dashboard.auth_rate_limit.max_burst',
      'dashboard.totp.enable',
    ]),
    createGroup('logs', [
      'log.level',
      'log.file_enable',
      'log.file_path',
      'log.file_max_mb',
      'trace.enable',
      'trace.db_path',
      'trace.db_max_mb',
      'trace.retention_days',
    ]),
    createGroup('tempStorage', ['temp_dir_max_size']),
    createGroup('t2iRendering', [
      't2i_template',
      't2i.use_file_service',
      't2i.active_template',
    ]),
  ].filter(
    (group) => Object.keys(group.metadata[group.key].items ?? {}).length > 0,
  );
});

const generalSystemConfigGroups = computed(() =>
  systemConfigGroups.value.filter(
    (group) =>
      group.key === 'runtime' ||
      group.key === 'logs' ||
      group.key === 'tempStorage',
  ),
);
const appearanceSystemConfigGroups = computed(() =>
  systemConfigGroups.value.filter((group) => group.key === 't2iRendering'),
);
const networkSystemConfigGroups = computed(() =>
  systemConfigGroups.value.filter((group) => group.key === 'network'),
);
const securitySystemConfigGroups = computed(() =>
  systemConfigGroups.value.filter((group) => group.key === 'webuiSecurity'),
);

watch(
  newApiKeyScopes,
  (scopes) => {
    const selectedScopes = new Set<ApiKeyScope>(scopes);
    const previousScopes = new Set<ApiKeyScope>(previousApiKeyScopes.value);

    if (selectedScopes.has('config')) {
      const includedScopeRemoved = configIncludedScopes.some(
        (scope) => previousScopes.has(scope) && !selectedScopes.has(scope),
      );

      if (includedScopeRemoved) {
        selectedScopes.delete('config');
      } else {
        for (const scope of configIncludedScopes) {
          selectedScopes.add(scope);
        }
      }
    }

    const nextScopes = availableScopes
      .map((scopeOption) => scopeOption.value)
      .filter((scope) => selectedScopes.has(scope));
    if (
      nextScopes.length !== scopes.length ||
      nextScopes.some((scope, index) => scope !== scopes[index])
    ) {
      newApiKeyScopes.value = nextScopes;
    }
    previousApiKeyScopes.value = [...nextScopes];
  },
  { deep: true, immediate: true },
);

const showToast = (message: string, color: ToastColor = 'success') => {
  toastStore.add({
    message,
    color,
    timeout: 3000,
  });
};

const formatDate = (value: string | number | null | undefined): string => {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '-';
  return dt.toLocaleString();
};

const getResponseErrorMessage = (error: unknown, fallback: string): string => {
  if (error && typeof error === 'object') {
    const response = (error as { response?: { data?: { message?: string } } })
      .response;
    const message = response?.data?.message;
    if (typeof message === 'string' && message) return message;
  }
  return fallback;
};

const updateServerClock = (data: Record<string, unknown>): void => {
  const serverUtcTime = data?.server_utc_time;
  const parsedServerTime = Date.parse(
    typeof serverUtcTime === 'string' ? serverUtcTime : '',
  );
  const parsedUtcOffset = Number(data?.server_utc_offset_minutes);
  serverUtcEpochMs.value = Number.isNaN(parsedServerTime)
    ? null
    : parsedServerTime;
  serverUtcOffsetMinutes.value = Number.isFinite(parsedUtcOffset)
    ? parsedUtcOffset
    : null;
  serverTimezone.value =
    typeof data?.server_timezone === 'string' && data.server_timezone
      ? data.server_timezone
      : null;
  serverClockAnchorMs.value =
    serverUtcEpochMs.value === null ? null : performance.now();
  serverClockTickMs.value = serverClockAnchorMs.value;
};

const refreshServerClock = async () => {
  try {
    const response = await systemConfigApi.get();
    if (response.data.status === 'ok') {
      updateServerClock(response.data.data);
    }
  } catch {
    updateServerClock({});
  }
};

const loadSystemConfig = async () => {
  systemConfigLoading.value = true;
  try {
    const res = await systemConfigApi.get();
    if (res.data.status !== 'ok') {
      showToast(
        res.data.message || tm('systemConfig.messages.loadFailed'),
        'error',
      );
      return;
    }
    const data = (res.data.data ?? {}) as SystemConfigResponseData;
    systemConfigData.value = data.config || {};
    systemConfigMetadata.value = data.metadata || {};
    updateServerClock(data);
    systemConfigLastSavedSnapshot.value = JSON.stringify(
      systemConfigData.value || {},
    );
    systemConfigRestartRequired.value = false;
  } catch (error) {
    showToast(
      getResponseErrorMessage(error, tm('systemConfig.messages.loadFailed')),
      'error',
    );
  } finally {
    systemConfigLoading.value = false;
  }
};

const saveSystemConfig = async (
  configOverride: Record<string, unknown> | null = null,
  headers: Record<string, string> = {},
  allow2faPrompt = true,
): Promise<{ success: boolean; requires2fa?: boolean }> => {
  if (systemConfigSaving.value || systemConfigLoading.value)
    return { success: false };

  systemConfigSaving.value = true;
  const configPayload: Record<string, unknown> = JSON.parse(
    JSON.stringify(configOverride || systemConfigData.value || {}),
  );
  try {
    const requestHeaders: Record<string, string> = { ...headers };
    const res = await runConfigMutationWithStepUp(
      (stepUp) => {
        if (stepUp) {
          Object.assign(requestHeaders, stepUpHeaders(stepUp));
        }
        return systemConfigApi.update(configPayload, {
          headers: requestHeaders,
          validateStatus: (status) =>
            (status >= 200 && status < 300) || status === 401,
        });
      },
      'default',
      requestStepUp,
    );
    if (!res) return { success: false };

    if (res.status === 401 && res.data?.data?.totp_required) {
      if (allow2faPrompt && !headers['X-2FA-Code']) {
        configSavePendingData.value = configPayload;
        configSavePendingHeaders.value = { ...requestHeaders };
        configSave2faError.value = '';
        configSave2faRotationHint.value =
          getConfigSaveRotationHint(configPayload);
        configSave2faDialogVisible.value = true;
        return { success: false, requires2fa: true };
      }
      configSave2faError.value = tmMeta(
        'system_group.system.dashboard.totp.configSaveError',
      );
      configSave2faDialogVisible.value = true;
      return { success: false, requires2fa: true };
    }

    if (res.data.status !== 'ok') {
      showToast(
        res.data.message || tm('systemConfig.messages.saveFailed'),
        'error',
      );
      return { success: false };
    }

    configSavePendingData.value = null;
    configSavePendingHeaders.value = {};
    configSave2faDialogVisible.value = false;
    configSave2faError.value = '';
    systemConfigData.value = configPayload;
    systemConfigLastSavedSnapshot.value = JSON.stringify(configPayload);
    await refreshServerClock();
    systemConfigRestartRequired.value = true;
    showToast(
      res.data.message || tm('systemConfig.messages.saveSuccess'),
      'success',
    );
    return { success: true };
  } catch (error) {
    showToast(
      getResponseErrorMessage(error, tm('systemConfig.messages.saveFailed')),
      'error',
    );
    return { success: false };
  } finally {
    systemConfigSaving.value = false;
  }
};

const scheduleSystemConfigAutoSave = (
  delay: number | FocusEvent = 250,
): void => {
  if (systemConfigLoading.value) return;
  if (systemConfigAutoSaveTimer.value) {
    clearTimeout(systemConfigAutoSaveTimer.value);
  }
  systemConfigAutoSaveTimer.value = setTimeout(async () => {
    systemConfigAutoSaveTimer.value = null;
    if (!systemConfigHasChanges.value) return;
    if (stepUpDialogOpen.value || configSave2faDialogVisible.value) return;
    if (systemConfigSaving.value) {
      scheduleSystemConfigAutoSave();
      return;
    }
    await saveSystemConfig();
  }, delay as number);
};

watch(
  systemConfigData,
  () => {
    if (!systemConfigHasChanges.value) return;
    scheduleSystemConfigAutoSave(700);
  },
  { deep: true },
);

const getConfigSaveRotationHint = (
  configPayload: Record<string, unknown>,
): string => {
  const dashboard = configPayload.dashboard;
  const totp =
    dashboard && typeof dashboard === 'object'
      ? (dashboard as { totp?: unknown }).totp
      : undefined;
  const postedSecret =
    totp && typeof totp === 'object'
      ? (totp as { secret?: unknown }).secret
      : undefined;
  if (postedSecret && typeof postedSecret === 'string' && postedSecret.trim()) {
    return tmMeta('system_group.system.dashboard.totp.configSaveRotationHint');
  }
  return '';
};

const handleConfigSave2faConfirm = async (payload: string) => {
  if (!configSavePendingData.value || configSave2faSaving.value) return;
  configSave2faSaving.value = true;
  configSave2faError.value = '';
  const headers: Record<string, string> = {
    ...configSavePendingHeaders.value,
    'X-2FA-Code': payload,
  };
  try {
    await saveSystemConfig(
      JSON.parse(JSON.stringify(configSavePendingData.value)),
      headers,
      false,
    );
  } finally {
    configSave2faSaving.value = false;
  }
};

const handleConfigSave2faCancel = () => {
  if (systemConfigLastSavedSnapshot.value) {
    try {
      systemConfigData.value = JSON.parse(systemConfigLastSavedSnapshot.value);
    } catch (_) {
      // Ignore invalid snapshots.
    }
  }
  configSavePendingData.value = null;
  configSavePendingHeaders.value = {};
  configSave2faError.value = '';
  configSave2faDialogVisible.value = false;
};

const loadApiKeys = async () => {
  try {
    const res = await apiKeyApi.list();
    if (res.data.status !== 'ok') {
      showToast(res.data.message || tm('apiKey.messages.loadFailed'), 'error');
      return;
    }
    apiKeys.value = (res.data.data || []) as ApiKey[];
  } catch (e) {
    showToast(
      getResponseErrorMessage(e, tm('apiKey.messages.loadFailed')),
      'error',
    );
  }
};

const requestApiKeyStepUp = () =>
  requestStepUp({
    action: 'identity.manage',
    resourceType: 'api-key',
    resourceId: 'collection',
  });

const copyCreatedApiKey = async () => {
  if (!createdApiKeyPlaintext.value) return;
  const ok = await copyToClipboard(createdApiKeyPlaintext.value);
  if (ok) {
    showToast(tm('apiKey.messages.copySuccess'), 'success');
  } else {
    showToast(tm('apiKey.messages.copyFailed'), 'error');
  }
};

const createApiKey = async () => {
  const selectedScopeSet = new Set<ApiKeyScope>(newApiKeyScopes.value);
  if (selectedScopeSet.has('config')) {
    for (const scope of configIncludedScopes) {
      selectedScopeSet.add(scope);
    }
  }
  const selectedScopes = availableScopes
    .map((scope) => scope.value)
    .filter((scope) => selectedScopeSet.has(scope));

  if (selectedScopes.length === 0) {
    showToast(tm('apiKey.messages.scopeRequired'), 'warning');
    return;
  }
  apiKeyCreating.value = true;
  try {
    const stepUp = await requestApiKeyStepUp();
    if (!stepUp) return;
    const payload: ApiKeyCreatePayload = {
      name: newApiKeyName.value,
      scopes: selectedScopes,
    };
    if (newApiKeyExpiresInDays.value !== 'permanent') {
      payload.expires_in_days = Number(newApiKeyExpiresInDays.value);
    }
    const res = await apiKeyApi.create(payload, {
      headers: stepUpHeaders(stepUp),
    });
    if (res.data.status !== 'ok') {
      showToast(
        res.data.message || tm('apiKey.messages.createFailed'),
        'error',
      );
      return;
    }
    createdApiKeyPlaintext.value = res.data.data?.api_key || '';
    newApiKeyName.value = '';
    newApiKeyExpiresInDays.value = 30;
    showToast(tm('apiKey.messages.createSuccess'), 'success');
    await loadApiKeys();
  } catch (e) {
    showToast(
      getResponseErrorMessage(e, tm('apiKey.messages.createFailed')),
      'error',
    );
  } finally {
    apiKeyCreating.value = false;
  }
};

const revokeApiKey = async (keyId: string) => {
  try {
    const stepUp = await requestApiKeyStepUp();
    if (!stepUp) return;
    const res = await apiKeyApi.revoke(keyId, {
      headers: stepUpHeaders(stepUp),
    });
    if (res.data.status !== 'ok') {
      showToast(
        res.data.message || tm('apiKey.messages.revokeFailed'),
        'error',
      );
      return;
    }
    showToast(tm('apiKey.messages.revokeSuccess'), 'success');
    await loadApiKeys();
  } catch (e) {
    showToast(
      getResponseErrorMessage(e, tm('apiKey.messages.revokeFailed')),
      'error',
    );
  }
};

const deleteApiKey = async (keyId: string) => {
  try {
    const stepUp = await requestApiKeyStepUp();
    if (!stepUp) return;
    const res = await apiKeyApi.delete(keyId, {
      headers: stepUpHeaders(stepUp),
    });
    if (res.data.status !== 'ok') {
      showToast(
        res.data.message || tm('apiKey.messages.deleteFailed'),
        'error',
      );
      return;
    }
    showToast(tm('apiKey.messages.deleteSuccess'), 'success');
    await loadApiKeys();
  } catch (e) {
    showToast(
      getResponseErrorMessage(e, tm('apiKey.messages.deleteFailed')),
      'error',
    );
  }
};

const restartAstrBot = async () => {
  const confirmed = await askForConfirmation(
    tm('system.restart.confirm'),
    confirmDialog,
  );
  if (!confirmed) return;

  try {
    await restartAstrBotRuntime(wfr.value, requestStepUp);
  } catch (error) {
    console.error(error);
  }
};

const openBackupDialog = () => {
  if (backupDialog.value) {
    backupDialog.value.open();
  }
};

const resetThemeColors = () => {
  primaryColor.value = defaultThemeColors.primary;
  secondaryColor.value = defaultThemeColors.secondary;
  localStorage.removeItem('themePrimary');
  localStorage.removeItem('themeSecondary');
  applyThemeColors(primaryColor.value, secondaryColor.value);
};

onMounted(async () => {
  await Promise.all([loadApiKeys(), loadSystemConfig()]);
  serverClockTimer.value = window.setInterval(() => {
    serverClockTickMs.value = performance.now();
  }, 1000);
  const hash = window.location.hash;
  if (hash.includes('settings-appearance')) {
    activeSettingsSection.value = 'appearance';
  } else if (hash.includes('settings-network')) {
    activeSettingsSection.value = 'network';
  } else if (hash.includes('settings-security')) {
    activeSettingsSection.value = 'security';
  } else if (hash.includes('settings-maintenance')) {
    activeSettingsSection.value = 'maintenance';
  } else if (hash.includes('settings-openapi')) {
    activeSettingsSection.value = 'openapi';
  }
});

onUnmounted(() => {
  if (serverClockTimer.value) {
    clearInterval(serverClockTimer.value);
    serverClockTimer.value = null;
  }
  if (systemConfigAutoSaveTimer.value) {
    clearTimeout(systemConfigAutoSaveTimer.value);
    systemConfigAutoSaveTimer.value = null;
  }
});
</script>

<style scoped>
.settings-page {
  --settings-border: rgba(17, 24, 39, 0.13);
  --settings-divider: rgba(17, 24, 39, 0.09);
  width: min(100%, 1120px);
  margin: 0 auto;
  padding: 36px 18px 48px;
}

.settings-page__header {
  margin-bottom: 28px;
}

.settings-layout {
  display: grid;
  grid-template-columns: 126px minmax(0, 1fr);
  gap: 34px;
  align-items: start;
}

.settings-main {
  min-width: 0;
}

.settings-nav {
  position: sticky;
  top: 76px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-top: 2px;
}

.settings-nav__item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 34px;
  padding: 6px 9px 6px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.64);
  cursor: pointer;
  font: inherit;
  font-size: 0.84rem;
  font-weight: 680;
  line-height: 1.25;
  text-align: left;
  text-decoration: none;
}

.settings-nav__item:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgb(var(--v-theme-on-surface));
}

.settings-nav__item--active {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgb(var(--v-theme-on-surface));
  font-weight: 760;
}

.settings-nav__item--active::before {
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 0;
  width: 2px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.52);
  content: '';
}

.settings-nav__item--active .settings-nav__icon {
  color: rgb(var(--v-theme-on-surface));
}

.settings-nav__icon {
  width: 15px;
  font-size: 15px;
  line-height: 1;
  text-align: center;
}

.settings-section {
  margin-bottom: 0;
  scroll-margin-top: 84px;
}

.settings-section:last-child {
  margin-bottom: 0;
}

.settings-section__heading {
  margin-bottom: 22px;
}

.settings-section__title {
  align-items: center;
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  font-size: 1.34rem;
  font-weight: 780;
  gap: 4px;
  letter-spacing: 0;
  line-height: 1.25;
}

.settings-section__content {
  min-width: 0;
}

.settings-list-card {
  overflow: hidden;
  border: 1px solid var(--settings-border);
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  box-shadow: none;
}

.settings-list-card:not(:last-child) {
  margin-bottom: 28px;
}

.settings-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(180px, 34%);
  gap: 18px;
  align-items: center;
  min-height: 60px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--settings-divider);
}

.settings-item:last-child {
  border-bottom: 0;
}

.settings-item--stack {
  display: block;
  min-height: auto;
}

.settings-item--stack > .settings-item__label {
  margin-bottom: 14px;
}

.settings-item--proxy {
  padding-bottom: 16px;
}

.settings-item--color {
  grid-template-columns: minmax(0, 1fr) minmax(360px, 44%);
}

.settings-item__title {
  display: flex;
  align-items: center;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.4;
}

.settings-item__subtitle {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.76);
  font-size: 0.78rem;
  line-height: 1.45;
}

.settings-item__control {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  width: 100%;
  max-width: 420px;
  justify-self: end;
}

.settings-item__control > * {
  min-width: 0;
}

.settings-item__control--wide {
  max-width: 520px;
}

.settings-item__control--proxy {
  justify-content: stretch;
  width: 100%;
  max-width: none;
}

.settings-item__control :deep(.v-btn) {
  min-height: 36px;
  border-radius: 10px;
  font-size: 0.86rem;
}

.settings-item__control :deep(.v-field) {
  border-radius: 10px;
  background-color: transparent;
}

.system-config-group {
  margin-bottom: 30px;
}

.system-config-group:last-child {
  margin-bottom: 0;
}

.system-config-group__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.system-config-group__title {
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.04rem;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.32;
}

.timezone-time-preview {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 5px;
  font-variant-numeric: tabular-nums;
}

.timezone-time-preview__item {
  padding: 3px 7px;
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  border-radius: 6px;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.055);
  font-size: 0.72rem;
  font-weight: 600;
  line-height: 1.3;
  white-space: nowrap;
}

.system-config-group :deep(.v-card) {
  margin-bottom: 0 !important;
  padding-bottom: 0 !important;
  overflow: hidden !important;
  border: 1px solid var(--settings-border) !important;
  border-radius: 10px !important;
  background: rgb(var(--v-theme-surface)) !important;
  box-shadow: none !important;
}

.system-config-group--with-cleanup :deep(.v-card) {
  border-bottom-right-radius: 0 !important;
  border-bottom-left-radius: 0 !important;
}

.system-config-group :deep(.config-section) {
  display: none;
}

.system-config-group :deep(.config-row) {
  min-height: 60px;
  padding: 12px 16px;
  border-radius: 0;
}

.system-config-group :deep(.config-row:hover) {
  background-color: transparent;
}

.system-config-group :deep(.property-info) {
  padding: 0 16px 0 0;
}

.system-config-group :deep(.property-info .v-list-item) {
  padding: 0;
}

.system-config-group :deep(.property-name) {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.4;
  white-space: normal;
}

.system-config-group :deep(.property-hint) {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.76) !important;
  font-size: 0.78rem;
  line-height: 1.45;
  opacity: 1 !important;
  white-space: normal;
}

.system-config-group :deep(.property-hint *) {
  opacity: 1 !important;
}

.system-config-group :deep(.property-hint a) {
  color: rgb(var(--v-theme-primary)) !important;
  opacity: 1 !important;
  text-decoration: none;
}

.system-config-group :deep(.config-input) {
  display: flex;
  justify-content: flex-end;
  min-width: 0;
  padding: 0;
}

.system-config-group :deep(.config-input > *) {
  width: 100%;
}

@media (min-width: 600px) {
  .system-config-group :deep(.config-input) {
    flex: 0 0 100%;
    max-width: 100%;
  }
}

.system-config-group :deep(.config-input .v-switch) {
  display: flex;
  justify-content: flex-end;
  width: auto;
  max-width: none;
  margin-left: auto;
}

.system-config-group :deep(.config-input .v-switch .v-input__control) {
  margin-left: auto;
}

.system-config-group :deep(.config-input .v-switch .v-selection-control) {
  justify-content: flex-end;
}

.system-config-group :deep(.v-field) {
  border-radius: 10px;
  background-color: transparent;
}

.system-config-group :deep(.config-divider) {
  margin-left: 0;
  border-color: var(--settings-divider);
}

.system-config-group :deep(.collapsed-config-toggle-row) {
  padding: 12px 18px 14px;
  border-top: 1px solid var(--settings-divider);
}

.system-config-group :deep(.collapsed-config-toggle) {
  margin-left: 0;
  color: rgb(var(--v-theme-primary));
  font-size: 0.84rem;
  font-weight: 650;
}

.api-key-panel {
  min-width: 0;
  font-size: 0.82rem;
}

.api-key-create-row {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(118px, 160px) auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.api-key-panel :deep(.v-field),
.api-key-panel :deep(.v-btn) {
  border-radius: 10px;
}

.api-key-panel :deep(.v-field) {
  min-height: 36px;
  font-size: 0.84rem;
  background-color: transparent;
}

.api-key-panel :deep(.v-field__input) {
  min-height: 36px;
  padding-top: 6px;
  padding-bottom: 6px;
  font-size: 0.84rem;
}

.api-key-panel :deep(.v-field-label) {
  font-size: 0.78rem;
}

.api-key-panel :deep(.v-btn) {
  min-height: 36px;
  padding: 0 14px;
  font-size: 0.84rem;
}

.api-key-panel :deep(.v-chip) {
  height: 30px;
  font-size: 0.8rem;
}

.api-key-plain {
  display: block;
  margin-top: 8px;
  word-break: break-all;
}

.api-key-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.api-key-name-cell {
  display: grid;
  gap: 4px;
}

.api-key-name-cell code {
  width: fit-content;
  color: rgba(var(--v-theme-on-surface), 0.66);
}

.settings-table-wrap {
  width: 100%;
  overflow-x: auto;
  border: 1px solid var(--settings-border);
  border-radius: 10px;
}

.settings-table-wrap :deep(.v-table) {
  font-size: 0.82rem;
}

.settings-table-wrap :deep(.v-table th) {
  height: 40px;
  padding: 0 10px;
  font-size: 0.82rem;
  font-weight: 700;
}

.settings-table-wrap :deep(.v-table td) {
  height: 44px;
  padding: 8px 10px;
  font-size: 0.82rem;
  line-height: 1.35;
}

.settings-table-wrap :deep(.v-table code) {
  font-size: 0.8rem;
}

.color-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.color-controls :deep(.v-input) {
  flex: 0 0 118px;
  min-width: 0;
}

.color-controls :deep(.v-btn) {
  flex: 0 0 auto;
  white-space: nowrap;
}

.settings-section__content :deep(.storage-cleanup-panel) {
  margin: 0;
}

.settings-section__content
  :deep(.storage-cleanup-panel--attached .storage-cleanup-card) {
  margin-top: -1px;
  border-top-left-radius: 0;
  border-top-right-radius: 0;
}

.system-config-restart-bar {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 30;
  width: min(420px, calc(100vw - 48px));
  border: 0;
  border-radius: 12px;
  background:
    linear-gradient(
      rgba(var(--v-theme-on-surface), 0.055),
      rgba(var(--v-theme-on-surface), 0.055)
    ),
    rgba(var(--v-theme-surface), 0.74);
  box-shadow: none;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}

.system-config-restart-bar__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  min-height: 48px;
  padding: 8px 12px 8px 16px;
}

.system-config-restart-bar__message {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: rgba(var(--v-theme-on-surface), 0.78);
  font-size: 0.84rem;
  font-weight: 560;
  line-height: 1.35;
}

.system-config-restart-bar__message .v-icon {
  color: rgba(var(--v-theme-on-surface), 0.54);
}

.system-config-restart-bar__button {
  flex: 0 0 auto;
  min-height: 32px;
  border: 0;
  border-radius: 9px;
  color: rgba(var(--v-theme-on-surface), 0.76) !important;
  background-color: rgba(var(--v-theme-on-surface), 0.1) !important;
  box-shadow: none !important;
  font-size: 0.82rem;
  font-weight: 650;
}

@media (max-width: 720px) {
  .settings-page {
    padding: 32px 14px 44px;
  }

  .settings-page__header {
    margin-bottom: 22px;
  }

  .settings-layout {
    grid-template-columns: 1fr;
    gap: 22px;
  }

  .settings-nav {
    position: static;
    flex-flow: row wrap;
    gap: 6px;
  }

  .settings-nav__item {
    border: 1px solid var(--settings-border);
    background: rgb(var(--v-theme-surface));
    min-height: var(--astrbot-control-size);
  }

  .settings-item,
  .api-key-create-row {
    grid-template-columns: 1fr;
  }

  .settings-item {
    gap: 12px;
    align-items: stretch;
    padding: 14px 16px;
  }

  .settings-item__control {
    max-width: none;
    justify-self: stretch;
  }

  .color-controls {
    justify-content: flex-start;
  }

  .color-controls :deep(.v-input) {
    flex: 1 1 120px;
    max-width: none;
  }

  .system-config-group :deep(.config-row) {
    padding: 14px 16px;
  }

  .system-config-group :deep(.property-info) {
    padding: 0;
  }

  .system-config-group :deep(.config-input) {
    justify-content: stretch;
    padding-top: 8px;
  }

  .system-config-group :deep(.config-input > *) {
    max-width: none;
  }

  .system-config-restart-bar__inner {
    align-items: center;
    gap: 8px;
    padding: 8px 10px 8px 12px;
  }

  .system-config-restart-bar__message {
    font-size: 0.8rem;
  }
}
</style>

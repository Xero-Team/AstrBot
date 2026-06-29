<template>
  <div class="proxy-selector">
    <h5 class="proxy-selector__title">
      {{ tm('network.proxySelector.title') }}
    </h5>
    <v-radio-group
      v-model="radioValue"
      class="proxy-selector__mode mt-2"
      :hide-details="true"
    >
      <v-radio :label="tm('network.proxySelector.noProxy')" value="0"></v-radio>
      <v-radio value="1">
        <template #label>
          <span>{{ tm('network.proxySelector.useProxy') }}</span>
          <v-btn
            v-if="radioValue === '1'"
            class="ml-2"
            size="x-small"
            variant="tonal"
            :loading="loadingTestingConnection"
            @click="testAllProxies"
          >
            {{ tm('network.proxySelector.testConnection') }}
          </v-btn>
        </template>
      </v-radio>
    </v-radio-group>
    <v-expand-transition>
      <div v-if="radioValue === '1'" class="proxy-selector__list">
        <v-radio-group
          v-model="githubProxyRadioControl"
          class="mt-2"
          :hide-details="true"
        >
          <v-radio
            v-for="(proxy, idx) in githubProxies"
            :key="proxy"
            color="success"
            :value="String(idx)"
          >
            <template #label>
              <div class="proxy-selector__option-label">
                <span class="proxy-selector__url">{{ proxy }}</span>
                <div v-if="proxyStatus[idx]" class="proxy-selector__status">
                  <v-chip
                    :color="proxyStatus[idx].available ? 'success' : 'error'"
                    size="x-small"
                    class="mr-1"
                  >
                    {{
                      proxyStatus[idx].available
                        ? tm('network.proxySelector.available')
                        : tm('network.proxySelector.unavailable')
                    }}
                  </v-chip>
                  <v-chip
                    v-if="proxyStatus[idx].available"
                    color="info"
                    size="x-small"
                  >
                    {{ proxyStatus[idx].latency }}ms
                  </v-chip>
                </div>
              </div>
            </template>
          </v-radio>
          <v-radio
            color="primary"
            value="-1"
            :label="tm('network.proxySelector.custom')"
          >
            <template v-if="String(githubProxyRadioControl) === '-1'" #label>
              <v-text-field
                v-model="selectedGitHubProxy"
                class="proxy-selector__custom-input"
                density="compact"
                variant="outlined"
                :placeholder="tm('network.proxySelector.custom')"
                :hide-details="true"
              >
              </v-text-field>
            </template>
          </v-radio>
        </v-radio-group>
      </div>
    </v-expand-transition>
  </div>
</template>

<script setup lang="ts">
import { statsApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import {
  readGitHubProxyState,
  writeGitHubProxyControl,
  writeGitHubProxyRadioValue,
  writeSelectedGitHubProxy,
  type GitHubProxyMode,
} from '@/utils/githubProxyStorage';
import { onMounted, ref, watch } from 'vue';

interface ProxyStatus {
  available: boolean;
  latency: number;
}

const { tm } = useModuleI18n('features/settings');

const githubProxies = [
  'https://edgeone.gh-proxy.com',
  'https://hk.gh-proxy.com',
  'https://gh-proxy.com',
  'https://gh.dpik.top',
] as const;

const githubProxyRadioControl = ref('0');
const selectedGitHubProxy = ref('');
const radioValue = ref<GitHubProxyMode>('0');
const loadingTestingConnection = ref(false);
const proxyStatus = ref<Record<number, ProxyStatus>>({});
const initializing = ref(true);

function getProxyByControl(control: string): string {
  if (control === '-1') {
    return '';
  }
  const index = Number.parseInt(control, 10);
  if (Number.isNaN(index)) {
    return '';
  }
  return githubProxies[index] || '';
}

function resolveLatency(response: unknown): number {
  const latency = (
    response as { data?: { data?: { latency?: unknown } } } | undefined
  )?.data?.data?.latency;
  const numericLatency =
    typeof latency === 'number'
      ? latency
      : Number.parseFloat(String(latency ?? 0));
  return Number.isFinite(numericLatency) ? Math.round(numericLatency) : 0;
}

watch(selectedGitHubProxy, (newVal) => {
  if (initializing.value) {
    return;
  }
  writeSelectedGitHubProxy(newVal || '');
});

watch(radioValue, (newVal) => {
  if (initializing.value) {
    return;
  }
  writeGitHubProxyRadioValue(newVal);
  if (newVal === '0') {
    selectedGitHubProxy.value = '';
    return;
  }
  if (githubProxyRadioControl.value !== '-1') {
    selectedGitHubProxy.value = getProxyByControl(
      githubProxyRadioControl.value,
    );
  }
});

watch(githubProxyRadioControl, (newVal) => {
  if (initializing.value) {
    return;
  }
  writeGitHubProxyControl(newVal);
  if (radioValue.value !== '1') {
    selectedGitHubProxy.value = '';
    return;
  }
  if (newVal !== '-1') {
    selectedGitHubProxy.value = getProxyByControl(newVal);
  }
});

onMounted(() => {
  initializing.value = true;

  const state = readGitHubProxyState();
  radioValue.value = state.radioValue;
  githubProxyRadioControl.value = state.control;
  if (state.radioValue === '1') {
    selectedGitHubProxy.value =
      state.control !== '-1'
        ? getProxyByControl(state.control)
        : state.selectedProxy;
  } else {
    selectedGitHubProxy.value = '';
  }

  initializing.value = false;
});

async function testSingleProxy(idx: number): Promise<void> {
  const proxy = githubProxies[idx];
  if (!proxy) {
    return;
  }

  try {
    const response = await statsApi.testGhproxy({
      proxy_url: proxy,
    });
    proxyStatus.value[idx] = {
      available: response.status === 200,
      latency: response.status === 200 ? resolveLatency(response) : 0,
    };
  } catch {
    proxyStatus.value[idx] = {
      available: false,
      latency: 0,
    };
  }
}

async function testAllProxies(): Promise<void> {
  loadingTestingConnection.value = true;
  try {
    await Promise.all(githubProxies.map((_proxy, idx) => testSingleProxy(idx)));
  } finally {
    loadingTestingConnection.value = false;
  }
}
</script>

<style scoped>
.proxy-selector {
  width: 100%;
  min-width: 0;
}

.proxy-selector__title {
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.4;
}

.proxy-selector__list {
  margin-left: 16px;
}

.proxy-selector :deep(.v-label) {
  min-width: 0;
  font-size: 0.875rem;
  line-height: 1.35;
  white-space: normal;
}

.proxy-selector__option-label {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 100%;
}

.proxy-selector__url {
  overflow-wrap: anywhere;
  word-break: normal;
}

.proxy-selector__status {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
}

.proxy-selector__custom-input {
  width: min(100%, 420px);
}
</style>

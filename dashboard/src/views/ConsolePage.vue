<script setup lang="ts">
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';
import { updatesApi } from '@/api/v1';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { useToast } from '@/utils/toast';
import { ref, watch } from 'vue';

const { tm } = useModuleI18n('features/console');
const toast = useToast();
const autoScrollEnabled = ref(
  localStorage.getItem('console_auto_scroll') !== 'false',
);
const pipDialog = ref(false);
const loading = ref(false);
const pipInstallPayload = ref({
  package: '',
  mirror: '',
});

watch(autoScrollEnabled, (value) => {
  localStorage.setItem('console_auto_scroll', String(value));
});

async function pipInstall(): Promise<void> {
  loading.value = true;
  try {
    const res = await updatesApi.installPip(pipInstallPayload.value);
    if (res.data.status === 'ok') {
      toast.success(res.data.message || tm('pipInstall.installSuccess'));
      pipDialog.value = false;
      return;
    }
    toast.error(res.data.message || tm('pipInstall.installFailed'));
  } catch (error) {
    toast.error(resolveErrorMessage(error, tm('pipInstall.requestFailed')));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="console-page">
    <div class="console-header">
      <div>
        <h1 class="text-h2 mb-1">{{ tm('title') }}</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          {{ tm('debugHint.text') }}
        </p>
      </div>
      <div class="d-flex align-center">
        <v-switch
          v-model="autoScrollEnabled"
          :label="
            autoScrollEnabled
              ? tm('autoScroll.enabled')
              : tm('autoScroll.disabled')
          "
          hide-details
          density="compact"
          inset
          color="primary"
          style="margin-right: 16px"
        ></v-switch>
        <v-dialog v-model="pipDialog" width="400">
          <template #activator="{ props: activatorProps }">
            <v-btn variant="plain" v-bind="activatorProps">{{
              tm('pipInstall.button')
            }}</v-btn>
          </template>
          <v-card>
            <v-card-title>
              <span class="text-h5">{{ tm('pipInstall.dialogTitle') }}</span>
            </v-card-title>
            <v-card-text>
              <v-text-field
                v-model="pipInstallPayload.package"
                :label="tm('pipInstall.packageLabel')"
                variant="outlined"
              ></v-text-field>
              <v-text-field
                v-model="pipInstallPayload.mirror"
                :label="tm('pipInstall.mirrorLabel')"
                variant="outlined"
              ></v-text-field>
              <small>{{ tm('pipInstall.mirrorHint') }}</small>
            </v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn
                color="blue-darken-1"
                variant="text"
                :loading="loading"
                @click="pipInstall"
              >
                {{ tm('pipInstall.installButton') }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </div>
    </div>
    <ConsoleDisplayer
      class="console-display"
      :auto-scroll="autoScrollEnabled"
    />
  </div>
</template>

<style scoped>
.console-page {
  height: 100%;
  margin: 0 auto;
  max-width: 1400px;
  padding: 24px;
  width: 100%;
}

.console-header {
  align-items: flex-start;
  display: flex;
  justify-content: space-between;
  margin-bottom: 24px;
}

.console-display {
  height: calc(100vh - 190px);
  width: 100%;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.fade-in {
  animation: fadeIn 0.2s ease-in-out;
}

@media (max-width: 768px) {
  .console-page {
    padding: 16px;
  }

  .console-header {
    flex-direction: column;
    gap: 12px;
  }
}
</style>

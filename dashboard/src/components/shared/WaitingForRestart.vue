<template>
  <v-dialog v-model="visible" persistent max-width="400">
    <v-card>
      <v-card-title>{{ t('core.common.restart.waiting') }}</v-card-title>
      <v-card-text>
        <v-progress-linear indeterminate color="primary"></v-progress-linear>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { statsApi } from '@/api/v1';
import { useI18n } from '@/i18n/composables';
import { useCommonStore } from '@/stores/common';
import { onBeforeUnmount, ref } from 'vue';

const { t } = useI18n();
const commonStore = useCommonStore();

const visible = ref(false);
const startTime = ref(-1);
const newStartTime = ref(-1);
const status = ref('');
const cnt = ref(0);
const retryTimer = ref<ReturnType<typeof window.setTimeout> | null>(null);
const hideTimer = ref<ReturnType<typeof window.setTimeout> | null>(null);

function clearTimer(timerRef: typeof retryTimer): void {
  if (timerRef.value !== null) {
    clearTimeout(timerRef.value);
    timerRef.value = null;
  }
}

function clearTimers(): void {
  clearTimer(retryTimer);
  clearTimer(hideTimer);
}

function reloadWithCacheBuster(): void {
  const url = new URL(window.location.href);
  url.searchParams.set('_r', Date.now().toString());
  window.location.replace(url.toString());
}

function stop(): void {
  clearTimers();
  visible.value = false;
  cnt.value = 0;
  newStartTime.value = -1;
}

async function checkStartTime(): Promise<number> {
  try {
    const response = await statsApi.startTime();
    const latestStartTime = Number(response.data.data.start_time);
    if (
      startTime.value !== -1 &&
      Number.isFinite(latestStartTime) &&
      latestStartTime !== startTime.value
    ) {
      newStartTime.value = latestStartTime;
      visible.value = false;
      clearTimers();
      reloadWithCacheBuster();
    }
  } catch {
    // backend may be unavailable during restart window
  }
  return newStartTime.value;
}

function scheduleNextTick(): void {
  clearTimer(retryTimer);
  retryTimer.value = window.setTimeout(() => {
    void timeoutInternal();
  }, 1000);
}

async function timeoutInternal(): Promise<void> {
  if (newStartTime.value === -1 && cnt.value < 60 && visible.value) {
    await checkStartTime();
    cnt.value += 1;
    scheduleNextTick();
    return;
  }

  if (cnt.value >= 60) {
    status.value = t('core.common.restart.maxRetriesReached');
  }
  cnt.value = 0;
  clearTimer(hideTimer);
  hideTimer.value = window.setTimeout(() => {
    visible.value = false;
  }, 1000);
}

async function check(initialStartTime: number | null = null): Promise<void> {
  clearTimers();
  newStartTime.value = -1;
  cnt.value = 0;
  visible.value = true;
  status.value = '';
  if (
    typeof initialStartTime === 'number' &&
    Number.isFinite(initialStartTime)
  ) {
    startTime.value = initialStartTime;
  } else {
    try {
      startTime.value = await commonStore.fetchStartTime();
    } catch {
      startTime.value = commonStore.getStartTime();
    }
  }
  scheduleNextTick();
}

defineExpose({
  check,
  stop,
});

onBeforeUnmount(() => {
  clearTimers();
});
</script>

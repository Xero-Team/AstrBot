<template>
  <div class="qr-code-viewer">
    <img v-if="imageSrc" :src="imageSrc" :alt="alt" class="qr-code-image" />
    <div v-else class="qr-code-empty">
      {{ emptyHint }}
    </div>
  </div>
</template>

<script setup lang="ts">
import QRCode from 'qrcode';
import { ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    value?: string;
    alt?: string;
    size?: number;
    margin?: number;
    emptyHint?: string;
  }>(),
  {
    value: '',
    alt: 'QR Code',
    size: 260,
    margin: 2,
    emptyHint: '暂无可用二维码',
  },
);

const imageSrc = ref('');

async function renderQRCode(rawValue: string | undefined): Promise<void> {
  const value = String(rawValue || '').trim();
  if (!value) {
    imageSrc.value = '';
    return;
  }

  try {
    imageSrc.value = await QRCode.toDataURL(value, {
      margin: props.margin,
      width: props.size,
      errorCorrectionLevel: 'M',
    });
  } catch {
    imageSrc.value = '';
  }
}

watch(
  () => props.value,
  (value) => {
    void renderQRCode(value);
  },
  { immediate: true },
);
</script>

<style scoped>
.qr-code-viewer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.qr-code-image {
  display: block;
  width: 180px;
  max-width: 100%;
  border-radius: 8px;
}

.qr-code-empty {
  color: rgba(0, 0, 0, 0.6);
  font-size: 12px;
}
</style>

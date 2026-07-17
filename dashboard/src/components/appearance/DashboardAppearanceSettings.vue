<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import { appearanceApi, type AppearanceWallpaper } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useAppearanceStore } from '@/stores/appearance';
import { useToastStore } from '@/stores/toast';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';

type Orientation = 'landscape' | 'portrait';

const { tm } = useModuleI18n('features/settings');
const appearance = useAppearanceStore();
const toast = useToastStore();
const confirmDialog = useConfirmDialog();
const wallpapers = ref<AppearanceWallpaper[]>([]);
const loading = ref(false);
const uploading = ref(false);
const uploadInput = ref<HTMLInputElement | null>(null);
const uploadOrientation = ref<Orientation>('landscape');

const fitOptions = [
  { title: tm('appearance.fit.cover'), value: 'cover' },
  { title: tm('appearance.fit.contain'), value: 'contain' },
];
const positionOptions = [
  { title: tm('appearance.position.center'), value: 'center center' },
  { title: tm('appearance.position.top'), value: 'center top' },
  { title: tm('appearance.position.bottom'), value: 'center bottom' },
  { title: tm('appearance.position.left'), value: 'left center' },
  { title: tm('appearance.position.right'), value: 'right center' },
];

const previewWallpaper = computed(() => {
  const selectedId =
    appearance.settings.landscapeWallpaperId ||
    appearance.settings.portraitWallpaperId;
  return wallpapers.value.find((wallpaper) => wallpaper.id === selectedId);
});

const previewImageStyle = computed(() => ({
  backgroundImage: previewWallpaper.value
    ? `url("${previewWallpaper.value.thumbnail_url}")`
    : 'none',
  backgroundPosition: appearance.settings.position,
  backgroundSize: appearance.settings.fit,
  filter: `brightness(${appearance.settings.brightness})`,
}));

const previewShadeStyle = computed(() => ({
  backgroundColor: `rgb(0 0 0 / ${appearance.settings.dim})`,
}));

const previewSurfaceStyle = computed(() => ({
  backgroundColor: `rgb(var(--v-theme-surface) / ${appearance.settings.surfaceOpacity})`,
}));

function selectionFor(orientation: Orientation): string {
  return orientation === 'landscape'
    ? appearance.settings.landscapeWallpaperId
    : appearance.settings.portraitWallpaperId;
}

function selectWallpaper(orientation: Orientation, wallpaperId: string): void {
  appearance.update(
    orientation === 'landscape'
      ? { landscapeWallpaperId: wallpaperId, enabled: true }
      : { portraitWallpaperId: wallpaperId, enabled: true },
  );
}

function openUpload(orientation: Orientation): void {
  uploadOrientation.value = orientation;
  uploadInput.value?.click();
}

async function loadWallpapers(): Promise<void> {
  loading.value = true;
  try {
    const response = await appearanceApi.list();
    wallpapers.value = response.data.data.items;
  } catch (error) {
    console.error('Failed to load Dashboard wallpapers:', error);
    toast.add({
      message: tm('appearance.messages.loadFailed'),
      color: 'error',
    });
  } finally {
    loading.value = false;
  }
}

async function uploadWallpaper(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const [file] = input.files || [];
  input.value = '';
  if (!file) return;

  uploading.value = true;
  try {
    const response = await appearanceApi.upload(file);
    const wallpaper = response.data.data;
    wallpapers.value = [wallpaper, ...wallpapers.value];
    selectWallpaper(uploadOrientation.value, wallpaper.id);
    toast.add({
      message: tm('appearance.messages.uploadSuccess'),
      color: 'success',
    });
  } catch (error) {
    console.error('Failed to upload Dashboard wallpaper:', error);
    toast.add({
      message: tm('appearance.messages.uploadFailed'),
      color: 'error',
    });
  } finally {
    uploading.value = false;
  }
}

async function removeWallpaper(wallpaper: AppearanceWallpaper): Promise<void> {
  const confirmed = await askForConfirmation(
    tm('appearance.confirmDelete'),
    confirmDialog,
  );
  if (!confirmed) return;

  try {
    await appearanceApi.delete(wallpaper.id);
    wallpapers.value = wallpapers.value.filter(
      (item) => item.id !== wallpaper.id,
    );
    appearance.clearWallpaper(wallpaper.id);
    toast.add({
      message: tm('appearance.messages.deleteSuccess'),
      color: 'success',
    });
  } catch (error) {
    console.error('Failed to delete Dashboard wallpaper:', error);
    toast.add({
      message: tm('appearance.messages.deleteFailed'),
      color: 'error',
    });
  }
}

function resetAppearance(): void {
  appearance.reset();
  toast.add({
    message: tm('appearance.messages.resetSuccess'),
    color: 'success',
  });
}

onMounted(() => {
  void loadWallpapers();
});
</script>

<template>
  <section class="appearance-settings">
    <div class="appearance-settings__heading">
      <div>
        <div class="appearance-settings__title">
          {{ tm('appearance.title') }}
        </div>
        <p class="appearance-settings__subtitle">
          {{ tm('appearance.subtitle') }}
        </p>
      </div>
      <v-btn size="small" variant="tonal" @click="resetAppearance">
        <v-icon start>mdi-restore</v-icon>
        {{ tm('appearance.reset') }}
      </v-btn>
    </div>

    <div
      class="appearance-preview"
      :class="{ 'appearance-preview--empty': !previewWallpaper }"
    >
      <div class="appearance-preview__image" :style="previewImageStyle" />
      <div class="appearance-preview__shade" :style="previewShadeStyle" />
      <div class="appearance-preview__surface" :style="previewSurfaceStyle">
        <span>{{ tm('appearance.preview') }}</span>
        <v-btn size="x-small" color="primary">
          {{ tm('appearance.sampleAction') }}
        </v-btn>
      </div>
    </div>

    <v-switch
      :model-value="appearance.settings.enabled"
      color="primary"
      hide-details
      :label="tm('appearance.enable')"
      @update:model-value="appearance.update({ enabled: $event === true })"
    />

    <div class="appearance-settings__controls">
      <v-select
        :model-value="appearance.settings.fit"
        :items="fitOptions"
        :label="tm('appearance.fit.label')"
        density="compact"
        hide-details
        variant="outlined"
        @update:model-value="appearance.update({ fit: $event })"
      />
      <v-select
        :model-value="appearance.settings.position"
        :items="positionOptions"
        :label="tm('appearance.position.label')"
        density="compact"
        hide-details
        variant="outlined"
        @update:model-value="appearance.update({ position: $event })"
      />
    </div>

    <div class="appearance-settings__sliders">
      <v-slider
        :model-value="appearance.settings.blur"
        :label="tm('appearance.blur')"
        :min="0"
        :max="24"
        :step="1"
        thumb-label
        @update:model-value="appearance.update({ blur: $event })"
      />
      <v-slider
        :model-value="appearance.settings.brightness"
        :label="tm('appearance.brightness')"
        :min="0.5"
        :max="1.5"
        :step="0.05"
        thumb-label
        @update:model-value="appearance.update({ brightness: $event })"
      />
      <v-slider
        :model-value="appearance.settings.dim"
        :label="tm('appearance.dim')"
        :min="0"
        :max="0.9"
        :step="0.05"
        thumb-label
        @update:model-value="appearance.update({ dim: $event })"
      />
      <v-slider
        :model-value="appearance.settings.surfaceOpacity"
        :label="tm('appearance.surfaceOpacity')"
        :min="0"
        :max="1"
        :step="0.05"
        thumb-label
        @update:model-value="appearance.update({ surfaceOpacity: $event })"
      />
    </div>

    <div
      v-for="orientation in ['landscape', 'portrait'] as const"
      :key="orientation"
      class="appearance-gallery"
    >
      <div class="appearance-gallery__heading">
        <div>
          <div class="appearance-gallery__title">
            {{ tm(`appearance.gallery.${orientation}.title`) }}
          </div>
          <p>{{ tm(`appearance.gallery.${orientation}.subtitle`) }}</p>
        </div>
        <v-btn
          size="small"
          color="primary"
          variant="tonal"
          :loading="uploading && uploadOrientation === orientation"
          @click="openUpload(orientation)"
        >
          <v-icon start>mdi-upload</v-icon>
          {{ tm('appearance.upload') }}
        </v-btn>
      </div>

      <div v-if="loading" class="appearance-gallery__empty">
        {{ tm('appearance.loading') }}
      </div>
      <div v-else-if="!wallpapers.length" class="appearance-gallery__empty">
        {{ tm('appearance.gallery.empty') }}
      </div>
      <div v-else class="appearance-gallery__grid">
        <article
          v-for="wallpaper in wallpapers"
          :key="wallpaper.id"
          class="appearance-wallpaper-card"
          :class="{
            'appearance-wallpaper-card--selected':
              selectionFor(orientation) === wallpaper.id,
          }"
        >
          <button
            type="button"
            class="appearance-wallpaper-card__select"
            :aria-label="tm('appearance.select')"
            @click="selectWallpaper(orientation, wallpaper.id)"
          >
            <img
              :src="wallpaper.thumbnail_url"
              :alt="tm('appearance.wallpaperAlt')"
            />
          </button>
          <div class="appearance-wallpaper-card__footer">
            <span>{{ wallpaper.width }} × {{ wallpaper.height }}</span>
            <v-btn
              size="x-small"
              icon="mdi-delete-outline"
              variant="text"
              color="error"
              :aria-label="tm('appearance.delete')"
              @click="removeWallpaper(wallpaper)"
            />
          </div>
        </article>
      </div>
    </div>

    <input
      ref="uploadInput"
      class="appearance-settings__file-input"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/gif"
      @change="uploadWallpaper"
    />
  </section>
</template>

<style scoped>
.appearance-settings {
  display: grid;
  gap: 20px;
  margin-top: 20px;
}

.appearance-settings__heading,
.appearance-gallery__heading,
.appearance-wallpaper-card__footer {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.appearance-settings__title,
.appearance-gallery__title {
  color: rgb(var(--v-theme-on-surface));
  font-size: 15px;
  font-weight: 600;
}

.appearance-settings__subtitle,
.appearance-gallery__heading p {
  color: rgba(var(--v-theme-on-surface), 0.66);
  font-size: 13px;
  margin: 4px 0 0;
}

.appearance-preview {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 12px;
  height: 144px;
  isolation: isolate;
  overflow: hidden;
  position: relative;
}

.appearance-preview--empty {
  background: linear-gradient(
    135deg,
    rgb(var(--v-theme-primary) / 0.3),
    rgb(var(--v-theme-surface))
  );
}

.appearance-preview__image,
.appearance-preview__shade,
.appearance-preview__surface {
  inset: 0;
  position: absolute;
}

.appearance-preview__image {
  background-repeat: no-repeat;
  opacity: 0.9;
  transform: scale(1.04);
}

.appearance-preview__surface {
  align-items: center;
  backdrop-filter: blur(6px);
  border: 1px solid rgb(var(--v-theme-on-surface) / 0.1);
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  justify-content: space-between;
  margin: 28px;
  padding: 16px;
}

.appearance-settings__controls,
.appearance-settings__sliders {
  display: grid;
  gap: 12px 24px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.appearance-gallery {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  padding-top: 20px;
}

.appearance-gallery__empty {
  color: rgba(var(--v-theme-on-surface), 0.64);
  padding: 16px 0 0;
}

.appearance-gallery__grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  margin-top: 14px;
}

.appearance-wallpaper-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 10px;
  overflow: hidden;
}

.appearance-wallpaper-card--selected {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary));
}

.appearance-wallpaper-card__select {
  background: transparent;
  border: 0;
  cursor: pointer;
  display: block;
  padding: 0;
  width: 100%;
}

.appearance-wallpaper-card__select img {
  aspect-ratio: 16 / 9;
  display: block;
  object-fit: cover;
  width: 100%;
}

.appearance-wallpaper-card__footer {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 12px;
  padding: 4px 6px 4px 8px;
}

.appearance-settings__file-input {
  display: none;
}

@media (max-width: 720px) {
  .appearance-settings__controls,
  .appearance-settings__sliders {
    grid-template-columns: 1fr;
  }
}
</style>

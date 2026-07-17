import { defineStore } from 'pinia';

export type WallpaperFit = 'cover' | 'contain';
export type WallpaperPosition =
  | 'center center'
  | 'center top'
  | 'center bottom'
  | 'left center'
  | 'right center';

export type AppearanceSettings = {
  enabled: boolean;
  landscapeWallpaperId: string;
  portraitWallpaperId: string;
  fit: WallpaperFit;
  position: WallpaperPosition;
  blur: number;
  brightness: number;
  dim: number;
  surfaceOpacity: number;
};

const STORAGE_KEY = 'astrbot:appearance:v1';

const defaultSettings = (): AppearanceSettings => ({
  enabled: false,
  landscapeWallpaperId: '',
  portraitWallpaperId: '',
  fit: 'cover',
  position: 'center center',
  blur: 0,
  brightness: 1,
  dim: 0.5,
  surfaceOpacity: 1,
});

function clamp(
  value: unknown,
  minimum: number,
  maximum: number,
  fallback: number,
) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(Math.max(parsed, minimum), maximum);
}

function readSettings(): AppearanceSettings {
  const defaults = defaultSettings();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const saved = JSON.parse(raw) as Partial<AppearanceSettings>;
    return {
      enabled: saved.enabled === true,
      landscapeWallpaperId:
        typeof saved.landscapeWallpaperId === 'string'
          ? saved.landscapeWallpaperId
          : '',
      portraitWallpaperId:
        typeof saved.portraitWallpaperId === 'string'
          ? saved.portraitWallpaperId
          : '',
      fit: saved.fit === 'contain' ? 'contain' : 'cover',
      position: isWallpaperPosition(saved.position)
        ? saved.position
        : defaults.position,
      blur: clamp(saved.blur, 0, 24, defaults.blur),
      brightness: clamp(saved.brightness, 0.5, 1.5, defaults.brightness),
      dim: clamp(saved.dim, 0, 0.9, defaults.dim),
      surfaceOpacity: clamp(
        saved.surfaceOpacity,
        0,
        1,
        defaults.surfaceOpacity,
      ),
    };
  } catch {
    return defaults;
  }
}

function isWallpaperPosition(value: unknown): value is WallpaperPosition {
  return (
    value === 'center center' ||
    value === 'center top' ||
    value === 'center bottom' ||
    value === 'left center' ||
    value === 'right center'
  );
}

function persist(settings: AppearanceSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export const useAppearanceStore = defineStore('appearance', {
  state: () => ({
    settings: readSettings(),
  }),

  getters: {
    active(state): boolean {
      return Boolean(
        state.settings.enabled &&
        (state.settings.landscapeWallpaperId ||
          state.settings.portraitWallpaperId),
      );
    },
    rootStyle(state): Record<string, string> {
      const settings = state.settings;
      const active = Boolean(
        settings.enabled &&
        (settings.landscapeWallpaperId || settings.portraitWallpaperId),
      );
      return {
        '--dashboard-surface-opacity': String(
          active ? settings.surfaceOpacity : 1,
        ),
        '--dashboard-wallpaper-dim': String(settings.dim),
        '--dashboard-wallpaper-blur': `${settings.blur}px`,
        '--dashboard-wallpaper-brightness': String(settings.brightness),
        '--dashboard-wallpaper-fit': settings.fit,
        '--dashboard-wallpaper-position': settings.position,
      };
    },
  },

  actions: {
    update(settings: Partial<AppearanceSettings>): void {
      this.settings = { ...this.settings, ...settings };
      persist(this.settings);
    },

    clearWallpaper(wallpaperId: string): void {
      this.update({
        landscapeWallpaperId:
          this.settings.landscapeWallpaperId === wallpaperId
            ? ''
            : this.settings.landscapeWallpaperId,
        portraitWallpaperId:
          this.settings.portraitWallpaperId === wallpaperId
            ? ''
            : this.settings.portraitWallpaperId,
      });
    },

    reset(): void {
      this.settings = defaultSettings();
      localStorage.removeItem(STORAGE_KEY);
    },
  },
});

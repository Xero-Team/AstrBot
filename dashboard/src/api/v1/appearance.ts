import { httpClient } from './shared';
import type { V1Response } from './shared';
import type { AppearanceWallpaper, AppearanceWallpaperListData } from './types';

export const appearanceApi = {
  list(): V1Response<AppearanceWallpaperListData> {
    return httpClient.get('/api/v1/appearance/wallpapers');
  },
  upload(file: File): V1Response<AppearanceWallpaper> {
    const formData = new FormData();
    formData.append('file', file);
    return httpClient.post('/api/v1/appearance/wallpapers', formData);
  },
  delete(wallpaperId: string): V1Response<{ id: string }> {
    return httpClient.delete(
      `/api/v1/appearance/wallpapers/${encodeURIComponent(wallpaperId)}`,
    );
  },
  imageUrl(wallpaperId: string): string {
    return `/api/v1/appearance/wallpapers/${encodeURIComponent(wallpaperId)}`;
  },
};

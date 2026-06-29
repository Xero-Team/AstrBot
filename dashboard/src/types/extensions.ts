import type { PluginData } from '@/api/v1';

export interface InstalledPlugin extends PluginData {
  name: string;
  repo?: string;
  version?: string;
  marketplace_name?: string;
  online_version?: string;
  has_update?: boolean;
  support_platforms?: string[];
  astrbot_version?: string;
  display_name?: string;
  desc?: string;
  short_desc?: string;
  logo?: string;
  i18n?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PluginMarketItem {
  name: string;
  trimmedName?: string;
  display_name?: string;
  desc?: string;
  description?: string;
  short_desc?: string;
  author?: unknown;
  repo?: string;
  installed?: boolean;
  version?: string;
  social_link?: string;
  tags?: string[];
  logo?: string;
  pinned?: boolean;
  stars?: number;
  updated_at?: string;
  download_url?: string;
  i18n?: Record<string, unknown>;
  astrbot_version?: string;
  category?: string;
  support_platforms?: string[];
  astrbot_support_checked?: boolean;
  astrbot_version_supported?: boolean;
  astrbot_support_message?: string;
  [key: string]: unknown;
}

export interface FailedPluginDetail {
  dir_name: string;
  name: string;
  display_name: string;
  error: string;
  traceback: string;
  reserved: boolean;
  [key: string]: unknown;
}

export interface PluginSourceItem {
  id?: string;
  name?: string;
  url: string;
}

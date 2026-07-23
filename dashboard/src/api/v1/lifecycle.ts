export const UPGRADE_RECOVERY_EVENT = 'astrbot-upgrade-recovery';
export const UPGRADE_RECOVERY_TOKEN_KEY = 'astrbot-upgrade-recovery-token';
export const PLUGIN_DASHBOARD_LIFECYCLE_EVENT =
  'astrbot:plugin-dashboard-lifecycle';

export type PluginDashboardLifecycleReason = 'plugin_changed' | 'logout';

export interface PluginDashboardLifecycleDetail {
  reason: PluginDashboardLifecycleReason;
  plugin_name?: string;
}

export function notifyPluginDashboardLifecycle(
  detail: PluginDashboardLifecycleDetail,
): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent<PluginDashboardLifecycleDetail>(
      PLUGIN_DASHBOARD_LIFECYCLE_EVENT,
      { detail },
    ),
  );
}

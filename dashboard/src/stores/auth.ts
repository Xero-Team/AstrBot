import { defineStore } from 'pinia';
import { router } from '@/router';
import {
  authApi,
  providerApi,
  statsApi,
  systemConfigApi,
  UPGRADE_RECOVERY_EVENT,
  UPGRADE_RECOVERY_TOKEN_KEY,
} from '@/api/v1';

interface AuthSessionData {
  username: string;
  token: string;
  password_upgrade_required?: boolean;
  md5_pwd_hint?: boolean;
  change_pwd_hint?: boolean;
}

interface SystemConfigPayload {
  config?: {
    platform?: unknown[];
  };
}

interface ProviderSourceRecord {
  id: string;
  provider_type?: string;
}

interface ProviderRecord {
  provider_type?: string;
  provider_source_id?: string;
  type?: string;
}

function getErrorMessage(error: unknown, fallback?: unknown): string {
  if (fallback instanceof Error) {
    fallback = fallback.message;
  } else {
    fallback = String(fallback ?? '');
  }

  if (!error || typeof error !== 'object') {
    return String(error ?? fallback);
  }
  const errorLike = error as {
    message?: string;
    response?: { status?: number; data?: { message?: string; data?: { totp_required?: boolean } } };
  };
  return errorLike.response?.data?.message || errorLike.message || String(fallback);
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    username: '',
    returnUrl: null as string | null,
  }),
  actions: {
    async finishAuthenticatedSession(data: AuthSessionData): Promise<void> {
      this.username = data.username;
      localStorage.setItem('user', this.username);
      localStorage.setItem('token', data.token);
      const passwordUpgradeRequired = Boolean(data?.password_upgrade_required);
      const md5PwdHint = Boolean(data?.md5_pwd_hint);
      const passwordWarning =
        Boolean(data?.change_pwd_hint) ||
        (md5PwdHint && !passwordUpgradeRequired);
      if (passwordWarning) {
        localStorage.setItem('change_pwd_hint', 'true');
        if (md5PwdHint && !passwordUpgradeRequired) {
          localStorage.setItem('md5_pwd_hint', 'true');
        } else {
          localStorage.removeItem('md5_pwd_hint');
        }
      } else {
        localStorage.removeItem('change_pwd_hint');
        localStorage.removeItem('md5_pwd_hint');
      }
      if (passwordUpgradeRequired) {
        localStorage.setItem('password_upgrade_required', 'true');
      } else {
        localStorage.removeItem('password_upgrade_required');
      }

      const onboardingCompleted = await this.checkOnboardingCompleted();
      this.returnUrl = null;
      if (passwordWarning) {
        void router.push('/auth/setup');
        return;
      }
      if (onboardingCompleted) {
        void router.push('/dashboard/default');
      } else {
        void router.push('/welcome');
      }
    },
    async login(
      username: string,
      password: string,
      code?: string,
      trustDeviceToken = false,
    ): Promise<'totp_required' | 'upgrade_recovery_required' | void> {
      try {
        const res = await authApi.login({
          username,
          password,
          code,
          trust_device_flag: trustDeviceToken,
        });

        if (res.data.status === 'error') {
          throw new Error(String(res.data.message || ''));
        }

        const sessionToken = String(res.data.data?.token || '');
        if (sessionToken) {
          const versionRes = await statsApi.version({
            headers: {
              Authorization: `Bearer ${sessionToken}`,
            },
            validateStatus: () => true,
          });
          const versionData = versionRes.data?.data || {};
          const coreVersion = String(versionData.version || '')
            .trim()
            .replace(/^v/i, '');
          const dashboardVersion = String(versionData.dashboard_version || '')
            .trim()
            .replace(/^v/i, '');
          if (
            versionRes.status < 400 &&
            coreVersion &&
            dashboardVersion &&
            coreVersion !== dashboardVersion
          ) {
            sessionStorage.setItem(UPGRADE_RECOVERY_TOKEN_KEY, sessionToken);
            window.dispatchEvent(
              new CustomEvent(UPGRADE_RECOVERY_EVENT, {
                detail: {
                  version: versionData.version,
                  dashboard_version: versionData.dashboard_version,
                  blocking: true,
                },
              }),
            );
            return 'upgrade_recovery_required';
          }
        }

        await this.finishAuthenticatedSession(res.data.data as unknown as AuthSessionData);
      } catch (error) {
        const typedError = error as { response?: { status?: number; data?: { data?: { totp_required?: boolean } } } };
        if (typedError.response?.status === 401 && typedError.response?.data?.data?.totp_required) {
          return 'totp_required';
        }
        throw new Error(getErrorMessage(error, error));
      }
    },
    async setup(
      username: string,
      password: string,
      confirmPassword: string,
    ): Promise<void> {
      try {
        const res = await authApi.setup({
          username,
          password,
          confirm_password: confirmPassword,
        });

        if (res.data.status === 'error') {
          throw new Error(String(res.data.message || ''));
        }

        await this.finishAuthenticatedSession(res.data.data as unknown as AuthSessionData);
      } catch (error) {
        throw (error instanceof Error ? error : new Error(String(error)));
      }
    },
    async checkOnboardingCompleted(): Promise<boolean> {
      try {
        // 1. 检查平台配置
        const platformRes = await systemConfigApi.get();
        const systemConfig = ((platformRes.data.data as SystemConfigPayload | undefined)?.config) || {};
        const hasPlatform = (systemConfig.platform || []).length > 0;
        if (!hasPlatform) return false;

        // 2. 检查提供者配置
        const providerRes = await providerApi.schema();
        const providers = Array.isArray(providerRes.data.data?.providers)
          ? (providerRes.data.data.providers as ProviderRecord[])
          : [];
        const sources = Array.isArray(providerRes.data.data?.provider_sources)
          ? (providerRes.data.data.provider_sources as unknown as ProviderSourceRecord[])
          : [];
        const sourceMap = new Map<string, string | undefined>();
        sources.forEach((s) => sourceMap.set(s.id, s.provider_type));
        
        const hasProvider = providers.some((provider) => {
          if (provider.provider_type) return provider.provider_type === 'chat_completion';
          if (provider.provider_source_id) {
            const type = sourceMap.get(provider.provider_source_id);
            if (type === 'chat_completion') return true;
          }
          return String(provider.type || '').includes('chat_completion');
        });

        return hasProvider;
      } catch (e) {
        console.error('Failed to check onboarding status:', e);
        return false;
      }
    },
    logout() {
      this.username = '';
      localStorage.removeItem('user');
      localStorage.removeItem('token');
      localStorage.removeItem('change_pwd_hint');
      localStorage.removeItem('md5_pwd_hint');
      localStorage.removeItem('password_upgrade_required');
      void authApi.logout().catch(() => undefined);
      void router.push('/auth/login');
    },
    has_token(): boolean {
      return Boolean(localStorage.getItem('token'));
    }
  }
});

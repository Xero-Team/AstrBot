import { generatedOptions, openApiV1, typed } from './shared';
import type {
  CreateApiKeyRequest,
  LoginRequest,
  SetupAuthRequest,
  TotpSetupRequest,
  UpdateAccountRequest,
} from './shared';
import type { AxiosRequestConfig } from './shared';
import { notifyPluginDashboardLifecycle } from './lifecycle';
import type {
  AuthLoginData,
  AuthSetupStatusData,
  OpenConfig,
  TotpSetupData,
} from './types';

export const authApi = {
  login(payload: LoginRequest) {
    return typed<AuthLoginData>(openApiV1.login({ body: payload }));
  },
  logout() {
    notifyPluginDashboardLifecycle({ reason: 'logout' });
    return typed<OpenConfig>(openApiV1.logout());
  },
  setupStatus(requestConfig?: AxiosRequestConfig) {
    return typed<AuthSetupStatusData>(
      openApiV1.getAuthSetupStatus(generatedOptions({}, requestConfig)),
    );
  },
  setup(payload: SetupAuthRequest) {
    return typed<OpenConfig>(openApiV1.setupAuth({ body: payload }));
  },
  setupTotp(payload?: TotpSetupRequest) {
    return typed<TotpSetupData>(openApiV1.setupTotp({ body: payload }));
  },
  recoverTotp() {
    return typed<TotpSetupData>(openApiV1.recoverTotp());
  },
  updateAccount(payload: UpdateAccountRequest) {
    return typed<OpenConfig>(openApiV1.updateAuthAccount({ body: payload }));
  },
};

export const apiKeyApi = {
  list() {
    return typed<OpenConfig[]>(openApiV1.listApiKeys());
  },
  create(payload: CreateApiKeyRequest) {
    return typed<{ api_key?: string }>(
      openApiV1.createApiKey({ body: payload }),
    );
  },
  revoke(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.revokeApiKey({ path: { key_id: keyId } }),
    );
  },
  delete(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteApiKey({ path: { key_id: keyId } }),
    );
  },
};

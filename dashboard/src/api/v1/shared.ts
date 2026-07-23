import type { AxiosRequestConfig, AxiosResponse } from 'axios';

import * as generatedOpenApiV1 from '../generated/openapi-v1';
import { client as openApiV1Client } from '../generated/openapi-v1/client.gen';
import { httpClient } from '../http';
import type { ApiEnvelope, OpenConfig } from './types';

openApiV1Client.setConfig({
  axios: httpClient,
  baseURL: '',
  throwOnError: true,
});

export { httpClient };
export { generatedOpenApiV1 as openApiV1 };
export type { AxiosRequestConfig, AxiosResponse };
export type { ApiEnvelope, OpenConfig };
export type * from '../generated/openapi-v1';

export type V1Response<T> = Promise<AxiosResponse<ApiEnvelope<T>>>;

export function typed<T>(response: Promise<unknown>): V1Response<T> {
  return response as unknown as V1Response<T>;
}

export function generatedOptions<T extends Record<string, unknown>>(
  options: T,
  requestConfig?: AxiosRequestConfig,
): T {
  return { ...options, ...(requestConfig || {}) } as T;
}

export function generatedQuery<T extends object>(
  params?: T,
): (T & Record<string, unknown>) | undefined {
  return params as (T & Record<string, unknown>) | undefined;
}

export function generatedFormData(
  formData: FormData | Record<string, unknown>,
): FormData | Record<string, unknown> {
  if (typeof FormData !== 'undefined' && formData instanceof FormData) {
    const body: Record<string, unknown> = {};
    formData.forEach((value, key) => {
      const existing = body[key];
      if (existing === undefined) {
        body[key] = value;
      } else if (Array.isArray(existing)) {
        existing.push(value);
      } else {
        body[key] = [existing, value];
      }
    });
    return body;
  }
  return formData;
}

export function botConfig(config: OpenConfig) {
  return { config };
}

export function providerConfig(config: OpenConfig) {
  return { config };
}

import {
  isDashboardStepUpRequired,
  type DashboardStepUpTarget,
} from '@/composables/useDashboardStepUp';

export type RequestDashboardStepUp = (
  target: DashboardStepUpTarget,
) => Promise<string | null>;

/** Build the header accepted by Dashboard high-risk endpoints. */
export function stepUpHeaders(token: string): Record<string, string> {
  return { 'X-AstrBot-Step-Up': token };
}

export async function runMutationWithStepUp<T>(
  operation: (stepUp?: string) => Promise<T>,
  target: DashboardStepUpTarget,
  requestStepUp?: RequestDashboardStepUp,
): Promise<T | null> {
  try {
    return await operation();
  } catch (error: unknown) {
    if (!isDashboardStepUpRequired(error) || !requestStepUp) {
      throw error;
    }

    const stepUp = await requestStepUp(target);
    if (!stepUp) {
      return null;
    }
    return operation(stepUp);
  }
}

export function runBotMutationWithStepUp<T>(
  operation: (stepUp?: string) => Promise<T>,
  resourceId: string,
  requestStepUp?: RequestDashboardStepUp,
): Promise<T | null> {
  return runMutationWithStepUp(
    operation,
    {
      action: 'platform.manage',
      resourceType: 'bot',
      resourceId,
    },
    requestStepUp,
  );
}

export function runProviderMutationWithStepUp<T>(
  operation: (stepUp?: string) => Promise<T>,
  resourceId: string,
  requestStepUp?: RequestDashboardStepUp,
): Promise<T | null> {
  return runMutationWithStepUp(
    operation,
    {
      action: 'provider.credentials.write',
      resourceType: 'provider',
      resourceId,
      configId: 'default',
    },
    requestStepUp,
  );
}

export function runConfigMutationWithStepUp<T>(
  operation: (stepUp?: string) => Promise<T>,
  configId: string,
  requestStepUp?: RequestDashboardStepUp,
): Promise<T | null> {
  return runMutationWithStepUp(
    operation,
    {
      action: 'provider.credentials.write',
      resourceType: 'instance',
      resourceId: configId,
      configId,
    },
    requestStepUp,
  );
}

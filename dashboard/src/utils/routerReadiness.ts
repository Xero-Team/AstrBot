import type { Router } from 'vue-router';

type LoggerLike = Pick<Console, 'warn'>;

export function waitForRouterReadyInBackground(
  router: Router,
  logger: LoggerLike = console,
): void {
  router.isReady().catch((error: unknown) => {
    logger.warn?.('Router did not become ready after fallback mount:', error);
  });
}

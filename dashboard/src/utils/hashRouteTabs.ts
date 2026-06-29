import type {
  RouteLocationNormalizedLoaded,
  RouteLocationRaw,
  Router,
} from 'vue-router';

import { EXTENSION_ROUTE_NAME } from '../router/routeConstants';

type LoggerLike = Pick<Console, 'warn'>;

export function getValidHashTab(
  routeHash: string | undefined,
  validTabs: readonly string[],
): string | null {
  const hash = String(routeHash || '');
  const tab = hash.includes('#') ? hash.slice(hash.lastIndexOf('#') + 1) : hash;
  return validTabs.includes(tab) ? tab : null;
}

export function createTabRouteLocation(
  route: Partial<RouteLocationNormalizedLoaded>,
  tab: string,
  fallbackRouteName = EXTENSION_ROUTE_NAME,
): RouteLocationRaw {
  const query = route.query ? { ...route.query } : {};
  const params = route.params ? { ...route.params } : undefined;

  if (route.name) {
    return {
      name: route.name,
      ...(params ? { params } : {}),
      query,
      hash: `#${tab}`,
    };
  }

  if (route.path) {
    return {
      path: route.path,
      query,
      hash: `#${tab}`,
    };
  }

  return {
    name: fallbackRouteName,
    ...(params ? { params } : {}),
    query,
    hash: `#${tab}`,
  };
}

export async function replaceTabRoute(
  router: Router,
  route: Partial<RouteLocationNormalizedLoaded>,
  tab: string,
  logger: LoggerLike = console,
): Promise<boolean> {
  try {
    await router.replace(createTabRouteLocation(route, tab));
    return true;
  } catch (error: unknown) {
    logger.warn?.('Failed to update extension tab route:', error);
    return false;
  }
}

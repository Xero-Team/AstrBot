import { MORE_GROUP_KEY } from '@/layouts/full/vertical-sidebar/sidebarItem';

const STORAGE_KEY = 'astrbot_sidebar_customization';

export interface SidebarCustomization {
  mainItems: string[];
  moreItems: string[];
}

export interface SidebarItem {
  title: string;
  icon?: string;
  children?: SidebarItem[];
  [key: string]: unknown;
}

interface ResolveSidebarOptions {
  cloneItems?: boolean;
  assembleMoreGroup?: boolean;
}

interface ResolvedSidebarItems {
  mainItems: SidebarItem[];
  moreItems: SidebarItem[];
  merged?: SidebarItem[];
  normalizedMainKeys: string[];
  normalizedMoreKeys: string[];
}

export function getSidebarCustomization(): SidebarCustomization | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? (JSON.parse(stored) as SidebarCustomization) : null;
  } catch (error) {
    console.error('Error reading sidebar customization:', error);
    return null;
  }
}

export function setSidebarCustomization(config: SidebarCustomization): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  } catch (error) {
    console.error('Error saving sidebar customization:', error);
  }
}

export function clearSidebarCustomization(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Error clearing sidebar customization:', error);
  }
}

export function resolveSidebarItems(
  defaultItems: SidebarItem[],
  customization: SidebarCustomization | null,
  options: ResolveSidebarOptions = {},
): ResolvedSidebarItems {
  const { cloneItems = false, assembleMoreGroup = false } = options;

  const normalizeKeys = (keys: unknown = []): string[] => {
    const list = Array.isArray(keys) ? keys : [];
    const deduped: string[] = [];
    const seen = new Set<string>();

    list.forEach((key) => {
      if (typeof key !== 'string') return;
      if (seen.has(key)) return;
      seen.add(key);
      deduped.push(key);
    });

    return deduped;
  };

  const all = new Map<string, SidebarItem>();
  const defaultMain: string[] = [];
  const defaultMore: string[] = [];

  defaultItems.forEach((item) => {
    if (item.children && item.title === MORE_GROUP_KEY) {
      item.children.forEach((child) => {
        all.set(child.title, cloneItems ? { ...child } : child);
        defaultMore.push(child.title);
      });
      return;
    }

    all.set(item.title, cloneItems ? { ...item } : item);
    defaultMain.push(item.title);
  });

  const hasCustomization = Boolean(customization);
  let mainKeys = hasCustomization
    ? normalizeKeys(customization?.mainItems || [])
    : [...defaultMain];
  let moreKeys = hasCustomization
    ? normalizeKeys(customization?.moreItems || [])
    : [...defaultMore];

  if (hasCustomization) {
    mainKeys = mainKeys.filter((title) => all.has(title));
    moreKeys = moreKeys.filter((title) => all.has(title));
  }

  if (hasCustomization) {
    const mainSet = new Set(mainKeys);
    moreKeys = moreKeys.filter((title) => !mainSet.has(title));
  }

  const used = hasCustomization
    ? new Set([...mainKeys, ...moreKeys])
    : new Set(defaultMain.concat(defaultMore));

  const mainItems = mainKeys
    .map((title) => all.get(title))
    .filter((item): item is SidebarItem => Boolean(item));

  if (hasCustomization) {
    defaultMain.forEach((title) => {
      if (!used.has(title)) {
        const item = all.get(title);
        if (item) mainItems.push(item);
      }
    });
  }

  const moreItems = moreKeys
    .map((title) => all.get(title))
    .filter((item): item is SidebarItem => Boolean(item));

  if (hasCustomization) {
    defaultMore.forEach((title) => {
      if (!used.has(title)) {
        const item = all.get(title);
        if (item) moreItems.push(item);
      }
    });
  }

  let merged: SidebarItem[] | undefined;
  if (assembleMoreGroup) {
    const children = cloneItems
      ? moreItems.map((item) => ({ ...item }))
      : [...moreItems];
    if (children.length > 0) {
      merged = [
        ...mainItems,
        {
          title: MORE_GROUP_KEY,
          icon: 'mdi-dots-horizontal',
          children,
        },
      ];
    } else {
      merged = [...mainItems];
    }
  }

  return {
    mainItems,
    moreItems,
    merged,
    normalizedMainKeys: [...mainKeys],
    normalizedMoreKeys: [...moreKeys],
  };
}

export function applySidebarCustomization(defaultItems: SidebarItem[]) {
  const customization = getSidebarCustomization();
  const { merged, normalizedMainKeys, normalizedMoreKeys } =
    resolveSidebarItems(defaultItems, customization, {
      cloneItems: true,
      assembleMoreGroup: true,
    });

  if (customization) {
    const rawMainKeys = Array.isArray(customization.mainItems)
      ? customization.mainItems
      : [];
    const rawMoreKeys = Array.isArray(customization.moreItems)
      ? customization.moreItems
      : [];
    const hasChanged =
      JSON.stringify(rawMainKeys) !== JSON.stringify(normalizedMainKeys) ||
      JSON.stringify(rawMoreKeys) !== JSON.stringify(normalizedMoreKeys);

    if (hasChanged) {
      setSidebarCustomization({
        mainItems: normalizedMainKeys,
        moreItems: normalizedMoreKeys,
      });
    }
  }

  return merged || defaultItems;
}

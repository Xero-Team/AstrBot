<template>
  <v-chip
    v-if="resultData"
    class="ref-chip"
    size="x-small"
    variant="flat"
    :style="chipStyle"
    :href="url"
    target="_blank"
    rel="noopener noreferrer"
    clickable
  >
    <v-icon start size="x-small" color="">mdi-link-variant</v-icon>
    <span>{{ domain || resultData.title || refIndex }}</span>
  </v-chip>
</template>

<script setup lang="ts">
import { computed, inject, unref, useSlots, type VNode } from 'vue';
import { safeHttpUrl } from '@/utils/safeUrl';

interface RefNodeProp {
  content?: string;
}

interface WebSearchResult {
  title?: string;
  url?: string;
}

type WebSearchResults = Record<string, WebSearchResult>;

const props = withDefaults(
  defineProps<{
    node?: RefNodeProp | null;
  }>(),
  {
    node: null,
  },
);

const slots = useSlots();
const injectedIsDark = inject('isDark', false);
const webSearchResults = inject<WebSearchResults | (() => WebSearchResults)>(
  'webSearchResults',
  () => ({}),
);

const isDark = computed(() => Boolean(unref(injectedIsDark)));
const refIndex = computed(() => {
  const nodeContent = props.node?.content?.trim();
  if (nodeContent) return nodeContent;
  return slotText(slots.default?.()).trim();
});

const resultData = computed(() => {
  if (!refIndex.value) return null;
  const results =
    typeof webSearchResults === 'function'
      ? webSearchResults()
      : webSearchResults;
  return results?.[refIndex.value] || null;
});

const url = computed(() => safeHttpUrl(resultData.value?.url) || '');

const domain = computed(() => {
  if (!url.value) return '';
  try {
    const urlObj = new URL(url.value);
    return urlObj.hostname.replace(/^www\./, '');
  } catch {
    // Malformed URL: there is no domain to display.
    return '';
  }
});

const chipStyle = computed(() => ({
  backgroundColor: isDark.value
    ? 'rgba(var(--v-theme-on-surface), 0.08)'
    : 'rgba(var(--v-theme-on-surface), 0.04)',
  color: isDark.value
    ? 'rgba(var(--v-theme-on-surface), 0.62)'
    : 'rgba(var(--v-theme-on-surface), 0.72)',
}));

function slotText(nodes: VNode[] = []): string {
  return nodes
    .map((node) => {
      if (typeof node.children === 'string') return node.children;
      if (Array.isArray(node.children))
        return slotText(node.children as VNode[]);
      return '';
    })
    .join('');
}
</script>

<style scoped>
.ref-chip {
  margin: 0 2px;
  cursor: pointer;
  text-decoration: none;
  transition: opacity;
  margin-left: 4px;
}

.ref-chip:hover {
  opacity: 0.8;
}
</style>

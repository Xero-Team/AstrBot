<script setup lang="ts">
import { MarkdownRender, enableKatex, enableMermaid } from 'markstream-vue';
import 'markstream-vue/index.css';
import 'katex/dist/katex.min.css';
import 'highlight.js/styles/github.css';

enableKatex();
enableMermaid();

defineProps<{
  content: string;
  typewriter?: boolean;
  class?: string;
}>();
</script>

<template>
  <MarkdownRender
    :content="content"
    :typewriter="typewriter"
    :class="$props.class"
  />
</template>

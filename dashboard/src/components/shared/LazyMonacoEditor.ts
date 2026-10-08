import { defineAsyncComponent } from 'vue';

/** Load the Monaco editor and its worker configuration on first use. */
export const LazyMonacoEditor = defineAsyncComponent(async () => {
  await import('@/utils/monacoLoader');
  const { VueMonacoEditor } = await import('@guolao/vue-monaco-editor');
  return VueMonacoEditor;
});

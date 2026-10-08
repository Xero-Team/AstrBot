import { defineAsyncComponent, h } from 'vue';

/** Load the Monaco editor and its worker configuration on first use. */
export const LazyMonacoEditor = defineAsyncComponent({
  loader: async () => {
    await import('@/utils/monacoLoader');
    const { VueMonacoEditor } = await import('@guolao/vue-monaco-editor');
    return VueMonacoEditor;
  },
  loadingComponent: {
    render: () =>
      h(
        'div',
        { class: 'monaco-editor-status', role: 'status' },
        'Loading editor…',
      ),
  },
  errorComponent: {
    render: () =>
      h(
        'div',
        { class: 'monaco-editor-status', role: 'alert' },
        'Unable to load editor.',
      ),
  },
  delay: 200,
  onError(error, retry, fail, attempts) {
    if (attempts <= 2) {
      retry();
      return;
    }
    console.error('Failed to load Monaco editor:', error);
    fail();
  },
});

import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config.ts';

const baseConfig =
  typeof viteConfig === 'function'
    ? viteConfig({
        command: 'serve',
        mode: 'test',
        isPreview: false,
        isSsrBuild: false,
      })
    : viteConfig;

export default mergeConfig(
  baseConfig,
  defineConfig({
    ssr: {
      noExternal: ['vuetify'],
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./tests/setup.vitest.ts'],
      // Component-mount tests share CPU with the parallel `make check-web`
      // targets; the 5s default is too tight when the host is saturated.
      testTimeout: 15_000,
      fsModuleCache: false,
      include: ['./tests/**/*.{vitest.ts,test.mjs}'],
      exclude: [
        './tests/setup.vitest.ts',
        './tests/subsetMdiFont.test.mjs',
        './tests/checkI18n.test.mjs',
        './tests/localPermissionPolicies.test.mjs',
      ],
      css: false,
      restoreMocks: true,
      clearMocks: true,
      coverage: {
        provider: 'v8',
        reportsDirectory: './coverage',
        reporter: ['text', 'json-summary'],
        include: ['src/**/*.ts'],
        exclude: [
          'src/api/generated/**',
          'src/**/*.d.ts',
          'src/main.ts',
          'src/views/**',
          'src/router/index.ts',
          'src/plugins/**',
          'src/composables/useMessages.ts',
          'src/composables/messagesTypes.ts',
          'src/composables/messageContent.ts',
          'src/composables/messageRecordMutations.ts',
          'src/composables/messageHistory.ts',
          'src/composables/chatRequestFlags.ts',
          'src/composables/chatStreamReader.ts',
          'src/composables/useProviderSources.ts',
          'src/utils/monacoLoader.ts',
          'src/utils/shiki.ts',
          'src/utils/shikiLimitedBundle.ts',
          'tests/**',
        ],
        thresholds: {
          lines: 93,
          functions: 95,
          statements: 92,
        },
      },
    },
  }),
);

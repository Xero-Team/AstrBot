import { fileURLToPath, URL } from 'url';
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
    resolve: {
      alias: [
        {
          // `public/favicon.svg` is served at the root path in Vite, but the
          // jsdom test environment does not resolve `/favicon.svg` to that
          // file. Map the absolute import (used as the default plugin icon
          // since the upstream favicon-as-default-icon change) to the file so
          // component tests can load it.
          find: /^\/favicon\.svg$/,
          replacement: fileURLToPath(new URL('./public/favicon.svg', import.meta.url)),
        },
      ],
    },
    ssr: {
      noExternal: ['vuetify'],
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./tests/setup.vitest.ts'],
      include: ['./tests/**/*.{vitest.ts,test.mjs}'],
      exclude: ['./tests/setup.vitest.ts', './tests/subsetMdiFont.test.mjs'],
      css: false,
      restoreMocks: true,
      clearMocks: true,
    },
  }),
);

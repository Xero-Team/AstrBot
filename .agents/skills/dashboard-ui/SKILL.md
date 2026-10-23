---
name: dashboard-ui
description: Build or modify the AstrBot Dashboard (Vue 3 + Vuetify 4). Use when editing dashboard/src, .vue SFCs, Vuetify components, Pinia stores, vue-router routes, dashboard i18n, or dashboard Vitest tests. Enforces the repo design-system guard and AstrBot theme tokens. Not for backend Python, the plugin SDK, or docs.
---

# AstrBot Dashboard UI

Fused guidance for the `dashboard/` app: Vue 3.5 SFCs, Vuetify 4 components,
Pinia 4 stores, vue-router 5 routes, vee-validate + yup forms, and Vitest 5
tests. It absorbs the useful parts of the upstream Vue/Vuetify skills into this
repository's actual conventions. Cite `AGENTS.md` for repository policy; do not
restate it.

Supporting library facts, the three-layer customization model, and upstream
provenance live in [REFERENCE.md](./REFERENCE.md). Load it when you need exact
Vuetify 4 / Vue 3.5 / Pinia 4 / vue-router 5 API behavior or migration notes.

## Locked

- Stack (do not silently upgrade or add parallel tooling): Vue `3.5.44`,
  Vuetify `4.3.0`, Pinia `4.1.0`, vue-router `5.4.0`, Vite `8.3.5`,
  Vitest `5.0.5`, `vee-validate` `4.15.1`, pnpm `12.11.2`. These are
  the versions in `dashboard/package.json`; Vuetify 3 answers are wrong here.
- Theme source of truth is `dashboard/src/design/theme.ts` (`themeNames`,
  `astrBotThemes`, semantic roles). Colours come from theme tokens
  (`primary`, `secondary`, `surface`, `on-surface`, `error`, ...) or the
  runtime CSS variables `rgb(var(--v-theme-*))`.
- Vuetify bootstrap is `dashboard/src/plugins/vuetify.ts`. It sets
  `defaultTheme: 'AstrBotLight'` and `defaults` for `VBtn`, `VCard`,
  `VTextField`, `VSelect`, `VTextarea`, `VListItem`, `VTooltip`, `VSnackbar`.
  Prefer adjusting a default there over restating a prop at each call site.
- The design-system guard `dashboard/scripts/check-design-system-source.mjs`
  is enforced. In Vue templates it rejects: static `style=`, unapproved
  `:style`, bare colours (`#hex`, `rgb()`, named colours) on
  `color`/`bg-color`/`base-color`/`text-color`/`icon-color`, `rounded` values
  outside `0|sm|md|circle`, `rounded-lg|xl|pill` utilities, and `elevation`
  above `4`.
- `dashboard/src/api/generated/openapi-v1/**` is generated. Its contract is
  `openspec/openapi-v1.yaml` at the repo root; regenerate, never hand-edit.
- Tests use `pnpm` scripts and `dashboard/tests/`. Vue SFC smoke tests are
  `*.vitest.ts`; browser tests are under `dashboard/tests/e2e/`.

## Open

- Component boundaries, composable names, and folder placement under
  `src/components/<feature>/`, `src/composables/`, `src/stores/`.
- Whether a change belongs in the theme, the Vuetify `defaults`, or ordinary
  template composition (see the decision table in REFERENCE.md).
- Store style: the repo currently uses option stores
  (`defineStore('id', { state, getters, actions })`); use a setup store only
  when the store needs composables or watchers, and keep the choice local.

## Workflow

1. **Confirm the target.** Read the nearest existing component, composable,
   or store before writing. Match its SFC order (`<script setup lang="ts">` →
   `<template>` → `<style>`), its props/emits contract style, and its i18n use.
2. **Plan boundaries for non-trivial work.** Give each component one
   responsibility. Keep route views and `App.vue` thin composition surfaces;
   move feature UI into `src/components/<feature>/` and state/side effects into
   `src/composables/use<Feature>.ts`. Split when a component owns 3+ distinct
   UI sections, mixes orchestration with large markup, or repeats a block.
3. **Implement with the right Vuetify layer.** Theme for colours/dark mode,
   `defaults`/`v-defaults-provider` for repeated props, SASS
   (`src/styles/`) for compile-time CSS-level values, a named slot for one
   internal element, template composition for arrangement. Customise through
   slots before reaching for CSS.
4. **Wire state and routing.** `useXxxStore()` inside setup/composables, not
   at module scope; destructure with `storeToRefs()`. In guards return a
   value (never call `next()`); decouple components from the router with
   `props: true` or `props: route => ({...})`; watch narrow sources such as
   `() => route.params.id`, not the whole `route`.
5. **Localize every user-facing string** with `useI18n()` / the module
   composable, and add the key to both `zh-CN` and `en-US`. Run
   `pnpm i18n:check`.
6. **Test next to the change.** Put `*.vitest.ts` under `dashboard/tests/`
   following the nearest existing file; use `@vue/test-utils` `mount` and the
   `tests/setup.vitest.ts` environment. Optimize only after behavior is
   correct.
7. **Self-check** the changed files against the Locked list, then run Verify.

## Vue rules for this repo

- Composition API with `<script setup lang="ts">` only. Keep source state
  minimal (`ref`/`shallowRef`); derive with `computed`; use watchers for side
  effects. Prefer `shallowRef` when deep reactivity is not needed.
- Type props/emits (`defineProps`/`defineEmits`/`defineModel`) and avoid
  `any` (`@typescript-eslint/no-explicit-any` is an error).
- Never use `v-html` on untrusted content; the rule is `error` and the
  DOMPurify path in `AGENTS.md` applies. Do not add a `v-html` that bypasses
  existing sanitization.
- Keep eslint clean: no floating promises, no nested ternaries, `eqeqeq`,
  consistent type imports (`import type`), no unused vars. Match the existing
  `dashboard/eslint.config.mjs` rules rather than disabling them.

## Vuetify 4 rules for this repo

- Vuetify 4 is a Material Design 3 breaking release. Do not paste Vuetify 3
  guidance: `density` (not `dense`), grid uses `gap`, typography variants were
  renamed, elevation is `0-5` (this repo caps templates at `4`). See
  REFERENCE.md for the exact list.
- Use the composables `useTheme`, `useDisplay`, `useDate`, `useLocale`; do
  not use `this.$vuetify` in `<script setup>`.
- Define `v-data-table` headers outside the template (inline arrays create a
  new identity every render). Use `v-data-table-server` for server paging,
  `v-data-table-virtual` (with `height`) for large unpaged lists.
- Toggle overlays with `v-model`, not `v-if`, to preserve transitions/state.
- Validate with `rules` (and `v-form` `validate-on`) — this repo already
  depends on `vee-validate` + `yup`; use the form library when a form is
  non-trivial instead of inventing a second validation path.

## Do not

- Add raw colours, inline visual styles, `rounded="lg"`, or `elevation > 4`
  in templates; extend the guard's `allowedDynamicStyles` map in the same
  change only if a dynamic style is genuinely unavoidable.
- Edit generated OpenAPI client files or change a route/schema without
  updating `openspec/openapi-v1.yaml` and regenerating.
- Import backend Python concepts into `astrbot/api/`, or add Dashboard
  imports into the plugin SDK (see `AGENTS.md` import boundaries).
- Add a new UI library, state manager, form library, or test runner without a
  current, stated need.
- Reintroduce a legacy theme alias, `platform_settings` wake policy, or any
  compatibility shim removed by this fork.

## Handoff

- Repository policy and security invariants: `AGENTS.md`, `SECURITY.md`.
- Skill tree rules and catalog: `.agents/skills/README.md`.
- Library reference and provenance: [REFERENCE.md](./REFERENCE.md).
- Vuetify MCP setup (OpenCode and Codex): REFERENCE.md → Vuetify MCP.
- Planning a larger change: `plan-issue`; smallest-change pass: `simplifier`.

## Verify

Run from `dashboard/` (focused) or use the root equivalents:

```bash
cd dashboard
pnpm typecheck
pnpm lint
pnpm test:design-system   # design-system guard + theme tests
pnpm test:vitest
pnpm i18n:check
pnpm build
```

From the repo root, `make check` also covers the Dashboard build and formatting.
For OpenAPI-touching changes, follow the generation sequence in `AGENTS.md`.

Keep this skill honest with `make check-dashboard-ui` (or
`node .agents/skills/dashboard-ui/scripts/check-skill.mjs`): it asserts the
frontmatter, required headings, referenced paths, and that the pinned versions
in the Locked section still match `dashboard/package.json`. Run it after any
dashboard dependency bump or skill edit.

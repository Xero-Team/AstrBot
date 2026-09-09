# Archify checkout overlay

Vendored from [tt-a1i/archify](https://github.com/tt-a1i/archify) at the
commit in `VENDOR.json`. Keep `LICENSE` and `THIRD_PARTY_NOTICES.md`.
The renderer is checkout-only; `.dockerignore` and hatch exclusions keep
it out of runtime and distribution artifacts.

Use the checkout's Node version. Rendering needs no dependencies;
`package-lock.json` supports brand-mark regeneration after a vendor bump.
Upstream scripts depending on excluded `../scripts/` or `test/` paths
are unavailable here. Use `make check-archify`.

Local patches are recorded in `VENDOR.json`; preserve them on vendor updates:

- `SKILL.md` is the fork's instruction entrypoint.
- Package scripts reference only bundled files.
- Brand capture accepts HTTPS and rejects private, loopback, and credentialed targets.
- HTML uses local/system fonts without fetching Google Fonts.

Set `--repo-root` to this checkout for evidence-backed architecture nodes.
Third-party marks follow `THIRD_PARTY_NOTICES.md`; Vue.js branding needs
independently permitted use. Do not run `scripts/check-update.mjs` during
ordinary authoring.

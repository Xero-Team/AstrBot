# Supply chain, plugins, and release hunting

## When to use

The target resolves dependencies, builds from untrusted contributions, runs CI,
creates release artifacts, loads plugins or Dashboard Extensions, or updates
deployed software. This domain covers trust handoffs from source and dependency
to the artifact a user runs.

Use `agent-and-llm.md` for plugin code that reaches agent tools, and
`client-side.md` for the extension iframe itself.

Source map: `astrbot/core/star/` (`plugin_runtime_loader.py`,
`plugin_lifecycle.py`, `plugin_package_installer.py`,
`dashboard_extension.py`, `plugin_extension_coordinator.py`, `updator.py`),
`astrbot/core/utils/pip_installer.py`,
`astrbot/core/utils/outbound_http.py`, `astrbot/api/dashboard.py`,
`astrbot/dashboard/api/plugin_dashboard.py`,
`astrbot/dashboard/services/plugin_page_session_service.py`,
`.github/workflows/`, `Dockerfile`, `compose*.yml`,
`scripts/napcat/`, `openspec/openapi-v1.yaml`.

## Core discipline

- A mutable or known-vulnerable dependency is not a finding by itself. Show who
  can influence resolution, which build consumes it, and what execution or
  release boundary follows. Dependency CVEs are out of scope per `SECURITY.md`.
- Follow integrity across every handoff: source identity, resolved inputs,
  build worker, artifact identity, test result, signature/attestation,
  promotion, and update consumer.
- CI configuration is authorization code. Establish which event triggered a
  workflow, whose code runs, which secrets and tokens exist, and what it may
  publish or mutate.
- A checksum fetched from the same untrusted location as the artifact does not
  establish independent integrity. Identify the trusted root and failure
  behavior.
- Plugin code runs in-process with full Python authority once installed; that
  is intended, not a finding. The boundaries that matter are install/update
  confinement, reserved-plugin protection, Dashboard Extension isolation, and
  agent/tool authorization for plugin-supplied capabilities.
- `confirmed` for in-repo control-flow failures with a bounded local check.
  `needs_validation` for branch protection, hosted-runner, registry, signing, or
  production promotion facts not observable in source.

## Plugin and extension classes

**Install path escape.** Install stages a directory or zip under a temporary
root, confines it to the staging/plugin roots, checks the metadata directory
name, rejects symlinks and non-directories, refuses reserved plugins, then
moves and loads. Check a zip entry that escapes extraction, a symlinked target,
a metadata name that selects another plugin's directory, a staging directory
that is discovered as a plugin, and an update that replaces a different plugin
than the one named.

**Reserved plugin protection.** Builtins load from
`astrbot/builtin_stars` and cannot be uninstalled, updated, or replaced; the
`reserved` flag is the sole discriminator. Check a user plugin that can claim a
builtin namespace, a path that treats a user plugin as reserved, and a command
or extension id reused across the two namespaces.

**Install requirements and pip.** A plugin's `requirements.txt` is forwarded to
the in-process pip installer, which injects the core constraints and installs
into the runtime. Check a requirements file that can override a core package, a
mirror or index injection, a resolver option smuggled through metadata, and a
failure that leaves a half-installed plugin active. Installing a plugin is an
operator action; a plugin's own malicious code is out of scope, but a platform
install-boundary failure is in scope.

**Update and download trust.** The updater validates the destination against
the plugin store or temp root, uses `extract_zip_safely`, and applies the
outbound download policy. Check a redirect follower, a URL whose scheme/host is
not validated, a proxy environment read, an archive that is extracted before
authenticity, and an update that runs install hooks before the new code is
validated.

**Dashboard Extension manifest.** Asset paths must be relative, unencoded,
dot-free, resolve inside the plugin root, and be regular files; the
`assets.v1.json` size/sha256 must match on-disk bytes; suffixes exclude HTML;
Actions are owner-bound and registered during `initialize()`, with atomic
publication and drain-before-deactivate. Check a symlink that escapes the
plugin root, a digest mismatch that is not enforced, an asset served with a
different content type, an Action registered outside the transaction, an
extension id reused by another owner, and a deactivation that races a live
handler.

**Plugin page session and CSP.** The page session stores only an HMAC digest,
is per-user bounded, and sets an `HttpOnly`/`Strict` exact-path cookie; the
shell CSP is `sandbox allow-scripts`, `default-src 'none'`, `connect-src
'none'`, `frame-ancestors 'self'`. Check a session that survives logout or
account switch, a bundle asset served to a cookie-bearing request, and a
`connect-src` or `frame-ancestors` weakening.

## CI and automation classes

**Untrusted code in a privileged workflow.** A pull request, issue comment,
fork, dependency update, or external event runs contributor-controlled code
with secrets, write tokens, deployment authority, or a trusted runner. Compare
trigger type, checkout ref, approval gate, environment protection, and
permission narrowing. A `pull_request_target` that checks out fork code is the
canonical candidate; `workflow_dispatch` and protected-branch `push` are not
attacker entry points.

**Workflow expression and command confusion.** Attacker-controlled branch
names, commit messages, issue fields, artifact names, matrix values, or
generated output entering `run:`, template expressions, paths, or privileged
inputs without canonical validation. A value in `env:` that an agentic step
reads is also an injection path.

**Cache, artifact, and workspace trust mixing.** A lower-trust job populates a
cache, artifact, shared workspace, or output that a higher-trust job restores
and executes or releases. Review cache keys and namespaces, producer identity,
digest binding, retention, and whether promotion re-resolves a mutable name.

**Automation identity overreach.** A job receives permissions beyond the
operation, repository, environment, or duration needed. Missing least privilege
alone is hardening; require a reachable privileged action.

**Repository-specific expectations.** This fork publishes no PyPI package or
versioned release assets; the nightly workflow may push a GHCR image and open a
prerelease. Do not report a missing PyPI publish, a missing versioned image, or
a `docs.astrbot.app` link as a vulnerability. Do report a workflow that can
publish the wrong artifact or bypass the maintainer gate.

## Release, generated-source, and build classes

**Build-to-promotion substitution.** Tests, review, signatures, and publication
refer to a mutable tag, filename, channel, or artifact id rather than the same
immutable digest. Check every copy, repack, architecture merge, and provenance
step between build and release.

**Generated source provenance.** NapCat models regenerate from the revision in
`scripts/napcat/napcat-revision.txt`; `make napcat-check` fails on a dirty
generated file. The Dashboard OpenAPI client and `docs/public/openapi.json` are
generated from `openspec/openapi-v1.yaml`. Check a hand-edited generated file, a
generator input that can change without review, a schema update that does not
move the client, and a build that consumes an unverified generated blob.

**Build-context inclusion.** Secrets, local configuration, repository
metadata, test fixtures, or developer artifacts enter a package or image
because the build context and ignore rules exceed intended inputs.
`.dockerignore` excludes `.agents/`; the Compose files intentionally build this
checkout as `astrbot:local`. Check a `.env`, `data/`, or credential file that
reaches an image layer, and a build step that fetches a mutable tag.

**Update metadata and rollback.** An updater that authenticates bytes but not
version, product, platform, channel, target path, expiry, or rollback state, or
that accepts metadata and payload from different transactions. Verify atomic
installation and recovery; a signature without policy binding is incomplete.

## Universal moves

- Walk backward from a released digest, installed plugin, or update to every
  source, generated input, credential, worker, cache, test result, and
  authorization decision.
- Compare untrusted and protected workflow events side by side. Mark each
  persisted channel crossing between them and require an immutable identity
  plus producer trust.
- Review revoked key, failed download, missing attestation, partial platform
  release, rollback, and registry outage paths. Failure policy is part of
  integrity.

## Validation rules

1. Name the lower-trust actor, controllable source/cache/artifact/metadata,
   consuming trusted job or updater, and the unauthorized publication, code
   inclusion, secret disclosure, or privileged execution.
2. Prove artifact or code identity across the broken handoff. A different
   mutable name or unbound digest must reach a real consumer.
3. For plugin install claims, cite the confinement check that is missing and
   the path that escapes. A plugin's own malicious behavior is out of scope.
4. For extension claims, cite the manifest/session/sandbox control that fails
   and the host authority or credential reachable.
5. Keep local validation bounded: a harmless fixture repository, dummy
   credential marker, local registry/config, and non-production namespace. Do
   not publish or alter a real release.
6. Verify hosted defaults for the pinned runner version. Unknown branch
   protection, runner, registry, or signing facts require `needs_validation`.

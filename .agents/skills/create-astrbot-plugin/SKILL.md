---
name: create-astrbot-plugin
description: Create, extend, or repair an AstrBot plugin (Star) using this fork's public SDK, including commands, configuration, AI calls, and Dashboard Extensions.
---

# Create an AstrBot plugin

Build the requested standalone plugin against this checkout.
Read [astrbot-plugin-contract.md](references/astrbot-plugin-contract.md)
and the checkout's `pyproject.toml` for the current Python floor.
Use [feature-patterns.md](references/feature-patterns.md) only for the
requested features; follow its linked development guides when API details
are needed.

Use `astrbot.api` and relative sibling imports. Keep optional dependencies,
configuration, localization, runtime Skills, and Dashboard assets out of a
minimal plugin until its behavior needs them. Own resources in
`initialize()` / `terminate()` and persist through the plugin storage API.

For a new package, prefer a sibling directory and the bundled scaffolder:

```bash
uv run python .agents/skills/create-astrbot-plugin/scripts/scaffold_plugin.py \
  --astrbot-root . --output ../astrbot_plugin_example \
  --name astrbot_plugin_example --author "Your Name" \
  --description "A short plugin description" --version 0.1.0
```

Choose routine details from the request; ask only about missing decisions
that materially change behavior. Inspect an existing directory before editing.
Use scaffold `--force` only for explicitly requested replacement.

Follow [verification.md](references/verification.md): run the contract checker
and focused lint/tests. Installation and reload checks use a disposable
checkout; the CLI resolves its root from the working directory, so
`ASTRBOT_ROOT` alone does not isolate installation.

Document usage and the Python floor in the plugin README. Report the package
path, checks run, and untested integrations. Out-of-tree plugin files belong
to that repository; do not include them in an AstrBot commit.

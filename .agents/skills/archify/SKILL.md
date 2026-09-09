---
name: archify
description: Render validated standalone HTML diagrams of this checkout, including architecture, workflows, sequences, data flow, lifecycles, and Mermaid conversions.
license: MIT
metadata:
  version: '2.17'
  author: tt-a1i
  based_on: Cocoon-AI/architecture-diagram-generator (MIT, v1.0)
  checkout: Xero-Team/AstrBot
  vendor_commit: 06dd052602dd9a369e4d034e24faef0917b5a60c
---

# Archify

Render code-backed diagrams with `node .agents/skills/archify/bin/archify.mjs`
from the checkout root. Keep specifications and artifacts in `.tmp/archify/`.
This vendored maintainer tool stays out of product builds.

Choose the diagram type from the requested relationship. Read
[authoring-contract.md](references/authoring-contract.md), the matching
`schemas/<type>.schema.json`, `schemas/common.schema.json`, and one matching
example under `examples/`. Examples supply field shapes, not repository facts.
New workflows use `schema_version: 2`.

Use current code as topology evidence. Omit brand marks unless a real product
has a permitted built-in or digest-pinned mark. Read
[brand-marks.md](references/brand-marks.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) only when using brands, and
[viewer-runtime.md](references/viewer-runtime.md) for optional viewer features.

Validate the final candidate and deliver it atomically:

```bash
node .agents/skills/archify/bin/archify.mjs validate <type> .tmp/archify/<name>.json --quality showcase --json
node .agents/skills/archify/bin/archify.mjs deliver <type> .tmp/archify/<name>.json .tmp/archify/<name>.html --quality showcase --json
```

Read [delivery-contract.md](references/delivery-contract.md) for browser
evidence and the handoff receipt. Distinguish deterministic validation,
automated browser evidence, and actual visual review. Report unavailable
checks honestly. Start preview or use `--open` only for a requested live window.

Runtime rendering needs no npm install. If the CLI fails, run `doctor`;
when changing the vendor tree, read [REFERENCE.md](REFERENCE.md) and run
`make check-archify`. Do not download vendor updates during diagram work.

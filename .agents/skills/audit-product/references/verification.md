# Verify findings before scoring

For each security or defect finding marked confirmed/likely, try to disprove
the claimed flow: inspect callers, guards, permissions, failure paths, and
tests. Correct or withdraw findings when another layer prevents the effect.

Before scoring, independently review every security/defect finding marked
confirmed or likely. Use a fresh read-only reviewer who did not author the
finding. Provide the finding ID, claim, cited paths, and SHA;
ask for confirmed, corrected, or rejected with code evidence. One reviewer
may check related findings together. Only the parent writes the ledger.
Apply corrections or rejections to the ledger before scoring. If independent
review is unavailable, record the finding as suspected with that limitation;
continue other audit work without claiming independent verification.

After confirming a root cause, search other owners likely to share it.
Check candidates against the same evidence bar, assign them to their runtime
owner, and record the seed finding. Skip a sweep only when the cause is
specific to one place, with a reason.

Before completing a module, record inspected paths, ratings or unassessed
dimensions, verification/variant outcomes, remaining gaps, and separate
Spec/Standards conclusions in its chapter. Validate the ledger.

## Security interpretation

Existing effective controls matter. Missing defense in depth is an info or
hardening note when another layer blocks the claimed attack. Broken
`AGENTS.md` invariants remain findings. OWASP lists guide investigation;
membership alone does not establish a vulnerability or severity.

Operator configuration is not attacker input without a demonstrated path
from a less-trusted actor. Vue interpolation escapes text; trace untrusted
HTML through sanitization to `v-html` before claiming XSS. Prompt injection
needs a crossed capability or data boundary, not merely an unwanted response.

## GitHub Actions

For `ops-supply-chain`, define the actor and reachable trigger. An external
actor without write access cannot automatically invoke protected push or
workflow_dispatch paths. Check:

- `pull_request_target` combined with untrusted checkout.
- Event expressions interpolated into shell `run:`.
- Comment-triggered commands without authorization.
- Unpinned third-party actions holding secrets or write permissions.
- Agent workflows reading untrusted instructions, hooks, config, or env data.

Record entry point, mechanism, impact, and required conditions without an
exploit payload. Methodology:
[workflow review](https://github.com/getsentry/skills/tree/main/skills/gha-security-review)
and [agentic actions](https://github.com/trailofbits/skills/tree/main/plugins/agentic-actions-auditor).

## Skills, plugins, and live interfaces

For `skills` / `star`, inspect instruction/content boundaries and scripts for
undeclared exfiltration, config poisoning, or mismatch with advertised
behavior. Documented attack descriptions are not themselves injection.

Use the [lab reference](lab.md) for live Dashboard evidence. CWV, axe-core
sampling, and agent-usability passes apply only when requested or relevant
to a demonstrated concern. Use matching official sources in
[standards.md](standards.md), record measured conditions, and mark unavailable
checks unassessed. Do not substitute a Lighthouse score for product quality
or a sample for full WCAG conformance.

Additional methodology:
[variant analysis](https://github.com/trailofbits/skills/tree/main/plugins/variant-analysis)
and [skill scanning](https://github.com/getsentry/skills/tree/main/skills/skill-scanner).
Cite these sources rather than vendoring their instruction trees.

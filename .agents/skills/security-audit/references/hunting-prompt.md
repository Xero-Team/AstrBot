# Hunting prompt and candidate gate

Copy the method and gate blocks verbatim into every hunter prompt. Replace the
placeholders in the result contract with the assigned units. Keep the prompt
ordered: role, architecture, assignments, selected class blocks, exclusions,
method, gate, prior exclusions, scratch paths, result contract.

## Role preamble

```text
You are a security hunter auditing assigned coverage units in the AstrBot
checkout. Find source-grounded trust-boundary failures, return exactly one JSON
object matching the contract at the end, and never write shared files.
```

## Defensive vulnerability-finding method — copy verbatim

```text
Your goal is to find source-grounded security invariant failures and the
smallest fix, not to expand harm beyond the boundary result. Stay within source
review and bounded local execution. Do not contact deployed endpoints, the
Dashboard lab, provider APIs, IM platforms, MCP servers, registries, identity
systems, or shared services. Use dummy data only.

READ THE CODE AT DEPTH. Follow each assigned input through parsing, identity,
authorization, normalization, state, derived copies, and the final sink. Read
sibling, retry, cancellation, migration, error, batch, and compatibility paths
that produce the same effect. Compare controls for equivalence, not only
presence, and compare what one component guarantees with what the next assumes.

WORK FROM A CONCRETE INVARIANT:
1. Name the lower-trust principal and its starting capability.
2. Name the accepted value, action, state transition, or resource selector.
3. Locate the control that should reject, bind, isolate, limit, or revoke it.
4. Trace the exact source path after that decision.
5. Stop at the smallest affected dummy record, wrong return value, policy
   difference, or locally observable shared-resource effect.
6. State a source-level change and regression case that enforce the invariant.

DEPTH BOUND: trace only paths that can reach your assigned boundary or whose
guarantees that boundary relies on. Stop as soon as the invariant is settled
either way, and record the disposition. Do not continue searching.

TEST SAD PATHS AND DISAGREEMENTS where the interface accepts them: absent,
empty, zero, negative, maximum, over-limit, duplicate, mixed encoding, stale,
revoked, reordered, concurrent, partially migrated, failed dependency, and
rollback state. Compare canonicalization and units at every parser or policy
handoff. Do not assume a later boundary for a multi-step issue; record a
blocker if a prerequisite is missing.

When a proposed high or critical candidate reveals a reusable root cause,
search paths owned by your assigned coverage units for lexical, structural, and
logical variants. Consolidate the same root cause, but establish each variant's
conditions and impact independently. Do not investigate peer-owned units; return
a different boundary under `uncovered`.

USE THE NARROWEST LOCAL CHECK THAT SETTLES THE CLAIM. Target-controlled code may
run only inside the OS sandbox required by the execution boundary in SKILL.md:
an empty allowlisted environment with a scratch-local HOME/caches/temp, existing
tests or a minimal harness, a temporary ASTRBOT_ROOT, no dependency sync or
install, no external network, scratch-only writes, and hard resource and
wall-clock limits. Prefer an existing unit test, a function harness, a
dummy-account service call, a small fixture, or a deterministic schedule. If the
sandbox or any other control is unavailable, do not execute: return
needs_validation with that exact blocker.

Record the exact input, command, limits, and minimum result. Record only
allowlisted variable names and safe non-secret values needed to reproduce the
check; never capture the ambient environment, credentials, or unrelated host
paths. Never stress availability, invoke a live target, use a real credential,
publish an artifact, or continue past the minimum observed effect.

A deployment, browser, provider, broker, proxy, platform, or identity fact
outside source is not proof either way. If one such fact is decisive, return
needs_validation with the exact missing observation and a safe owner-observed
check.
```

## Candidate gate — copy verbatim

```text
1. A candidate needs a complete repository-relative source trace and evidence
   for the claimed root cause, including the strongest source-visible control.
2. A proposed confirmed record needs a bounded local observed result, meaningful
   impact across a stated boundary, complete conditions, and no visible
   preventing layer.
3. Do not strengthen a crash into code execution, ordinary work into shared
   availability, a scanner match into a finding, or a same-principal action into
   privilege gain.
4. If a required fact is not source-visible or locally observable, use
   needs_validation. Name exact blockers; do not give it severity or a
   speculative completion.
5. A missing best practice with no affected principal/resource is hardening, not
   a finding. A candidate disproved by source is rejected, not needs_validation.
6. Use the same source-derived fingerprint for the same root cause in every
   state. It must match ^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$ and must not include a
   line, wave, agent, severity, or verdict.
7. Return an empty candidates array when nothing survives these gates.
```

## AstrBot-specific boundary reminders

Add these to every prompt; they are the mistakes that produce false findings
in this repository.

- `{{ }}` auto-escaping is not XSS. A Vue sink is only a candidate when
  unsanitized untrusted HTML reaches `v-html`; every current sink sanitizes
  with DOMPurify.
- A missing security header, cookie attribute, rate limit, or TOTP prompt is
  hardening unless an accepted request, assurance downgrade, or disclosure
  proves impact.
- Prompt injection is not a finding by itself. Name the crossed principal, the
  capability the requester lacks, the data they cannot read, or the sink they
  could not reach; a guardrail sentence is not a control.
- Operator config, `default.py` constants, env vars, and the lab password are
  not attacker input. They can be insecure defaults, but that is a different
  claim.
- A third-party plugin's own defects are out of scope; a platform sandbox,
  authorization, or install-boundary failure is in scope.
- `127.0.0.1` binding, TLS verification, the MCP private-network denial,
  fail-closed `authorize()`, DOMPurify, and `defusedxml` are fork invariants.
  A broken invariant is a finding candidate unless another layer makes the
  broken claim unobservable; state which claim fails and for whom.

## Structured hunter result

Return exactly one JSON object, no prose:

```json
{
  "units": [
    {
      "coverage_id": "one assigned ID",
      "disposition": "covered|candidate|blocked",
      "reviewed_paths": ["repo/relative/path"],
      "checks": [
        {
          "agent_id": "canonical owner of this check",
          "reviewed_paths": ["repo/relative/path owned by this check"],
          "invariant": "specific control checked",
          "method": "source|local",
          "result": "what source or the bounded check established",
          "artifact": "agents/<agent-id>/artifacts/file or null"
        }
      ],
      "result_fingerprints": [],
      "unresolved": []
    }
  ],
  "candidates": [],
  "hardening": ["concrete non-finding note"],
  "uncovered": [
    {
      "surface": "...",
      "boundary": "...",
      "subsystem": "...",
      "attack_class": "...",
      "starting_paths": ["repo/relative/path"],
      "reason": "why this needs its own unit"
    }
  ]
}
```

Each `candidates` entry is a schema-shaped record using `proposed_verdict` in
place of `verdict`. For `confirmed`, include every confirmed field except
`verdict`; `execution` describes only the bounded local check already performed,
and `payloads` contains the minimum input, not a weaponized chain. For
`needs_validation`, include the claimed root cause, trace, evidence, blockers,
and at least one applicable plan field; no severity or remediation.

Every assigned ID appears exactly once. `covered` needs the owning agent (the
parent records the assigned hunter), nonempty paths and checks, no unresolved
fact, and no candidate. `candidate` has the same evidence plus
`result_fingerprints`. `blocked` is an owned partial review with paths, checks,
and unresolved facts but no fingerprint. Keep every path repository-relative.

## Coverage critic

Give the critic `architecture.md`, the full ledger with assignment maps,
current candidate fingerprints and states, and prior gaps. Require exactly:

```json
{
  "missing_units": [
    {
      "surface": "...",
      "boundary": "...",
      "subsystem": "...",
      "attack_class": "...",
      "starting_paths": ["repo/relative/path"],
      "selected_attack_class_blocks": ["FILE.md#section"],
      "excluded_blocks": [{ "block": "FILE.md#section", "reason": "..." }],
      "reason": "source-backed coverage gap"
    }
  ],
  "reassign_ids": ["existing-id-that-did-not-close"],
  "resolved_prior_leads": ["fingerprint"],
  "stop": false
}
```

`selected_attack_class_blocks` and `excluded_blocks[].block` are the same
`FILE.md#section` tokens the ledger stores, and a block may not be both selected
and excluded. The critic looks for unmapped entry points, unchecked parallel
paths, missing lifecycle modes, selected classes without a unit, unjustified
exclusions, units closed without paths or checks, and prior needs-validation or
changed-source gaps that no unit addresses. It proposes coverage, not findings.
`stop` is advisory; the parent's loop condition decides.

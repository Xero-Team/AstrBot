# Agent, LLM, tool, and MCP hunting

## When to use

The target involves the local agent runtime, prompt assembly, tool dispatch,
subagents, BTW work sessions, WebChat runs, MCP, or any path where model output,
retrieved content, memory, or a tool result drives a capability. The important
flow is untrusted content → model or memory → capability, authority, or sink.

Use it with the web and data references: transport, access control, query
construction, filesystem use, and rendering remain ordinary trust boundaries.
This file covers the model-specific delegation layer.

Source map: `astrbot/core/pipeline/` (`bootstrap.py`, `waking_check/`,
`turn_router.py`, `admission_check/`, `process_stage/`),
`astrbot/core/agent/` (`conversation_loop.py`, `runners/`,
`tool_executor.py`, `mcp_client.py`, `handoff.py`, `btw/`),
`astrbot/core/astr_agent_tool_exec.py`, `astrbot/core/tool_catalog.py`,
`astrbot/core/astr_main_agent.py`, `astrbot/core/astr_main_agent_resources.py`,
`astrbot/core/subagent_orchestrator.py`,
`astrbot/core/webchat/run_coordinator.py`.

## Core discipline

- Prompt injection alone is not a finding. Require a code-level boundary
  failure: content reaches another principal's context, invokes authority the
  requester lacks, discloses data they cannot read, or drives a sink they
  cannot reach directly.
- Model output, memory, tool descriptions, MCP results, and plugin-supplied
  prompt requests are untrusted. Point to the code that grants authority,
  trusts output, writes durable state, or feeds a sink.
- A guardrail prompt is not a security boundary. Count only deterministic
  checks, resource-scoped authorization, isolation, binding, and constrained
  credentials.
- Name the attacker, affected principal, execution identity, resource, exact
  action, authority used, and observable impact. An intentional request to use
  the requester's existing authority is not a delegation defect just because a
  model executes it.
- Authorization and action binding are separate controls. Attacker content
  that causes an action under a victim's valid authority is an action-binding
  failure when the victim did not intentionally request or approve that exact
  action.
- `confirmed` requires source evidence and a bounded local result. Use
  `needs_validation` when provider, deployment, model, renderer, or identity
  behavior is not observable locally.

## Pipeline and authorization classes

**Wake and route confusion.** `route_turn` owns `wake_reasons`, `route_kind`,
`should_run_command`, and `should_run_llm`; adapter extras are overwritten.
`llm_access` defaults to `prefix`; `reply_to_bot` requires a quoted reply whose
sender is the bot; inbound flush flags are stripped; a matched command wins and
an incomplete command never falls through to the LLM. Check an adapter field
that can forge a wake, a continuation window that outlives its turn, a
`reply_to_bot` path that accepts a stranger's quote, and a command prefix
collision with `llm_access`.

**Admission and rate limits.** Blocked senders may run only the explicit
unblock/status handlers; WebChat bypasses admission and relies on its own
principal normalization; the rate-limit registry is bounded. Check a WebChat
path that inherits an IM admission decision, a blocked sender that reaches an
LLM or plugin handler, and a bypass obtained through a claimed operator action
rather than the operator principal.

**Principal normalization.** `_attach_authorization` mints `Subject`,
`Resource.session(config_id, umo)`, and `AuthContext` once. WebChat principals
come only from verified API-key or Dashboard extras; a plain `sender_id` is a
guest. Check a later stage that trusts a message field, a thread run that takes
`umo` from the client, and an instance-tool elevation read from an
attacker-influenced source.

**Command identity.** `command_id` is
`{plugin}:{original path with dots}`; `alter_cmd` and `command_configs` resolve
by it, and unmatched rows are deleted. Check a handler-name or short-name
fallback, a takeover that lets one plugin claim another's public path, a rename
that shadows an `llm_access` prefix, and a permission filter that is missing or
inserted after dispatch.

## Tool and action classes

**Tool-argument injection into a sink.** Model-produced arguments reach SQL,
shell, file, URL-fetch, or privileged APIs. Treat the tool schema as input
parsing, then follow each field from decoded call to sink. Structured output
narrows shape; it does not establish authorization, safe paths, URLs, or query
semantics. `computer/process_sandbox` is the containment for computer tools,
not for plugin `@llm_tool` functions, which run in-process.

**Dispatch authorization.** `_authorize_execution` requires subject, resource,
auth context, and the authorization service; each declared action must be
allowed, and a tool with no declared action is denied. It checks
`Resource.named("tool", tool.name, config_id=...)`, not the session resource.
Check a dispatch branch that runs before the gate, a missing action declaration
that is treated as allowed, a loop-policy re-check that can be skipped, and a
background or handoff tool that bypasses either gate.

**Excessive agency and confused deputy.** A tool handler uses a service
identity or plugin credential, but does not re-check the requesting principal's
permission on the named resource. Verify both the effective identity and
whether the caller could perform the exact operation through the normal
interface. A shared credential with enforced per-query scope is not a defect.

**Action and approval binding.** WebChat step-up tokens are bound to session,
action, resource, context digest, and one use. Check a token that survives a
retry, a resumed run, an interrupt, an action mutation, a different resource,
or another run on the same socket; a token accepted for an action outside the
instance-tool allowlist; and a side effect produced by attacker content that the
victim never requested.

**Tool schema and dispatcher disagreement.** MCP tool names are allocated as
`mcp_{readable}_{blake2s(server\0tool)}` with collision refusal, and the
original server/tool identity is preserved. Check a schema that accepts
aliases, extra fields, duplicate keys, coercions, or free-form objects that the
handler interprets differently; a rename that loses server identity; and a
catalog refresh that replaces part of the toolset.

**Read-only classification.** MCP read/write actions trust the server's
`readOnlyHint`; an unannotated tool is a write. A malicious server can declare
a write tool read-only. Treat this as a candidate only when the resulting action
crosses a principal or resource boundary the read scope does not grant.

**Unbounded delegation and spend.** A bounded request can enqueue repeated
model calls, sends, tool loops, or paid provider work without a per-request
budget, cancellation, or idempotency control. Confirm impact on shared cost,
quotas, other users, or durable state. Do not test by exhausting a service.

## MCP classes

**Remote URL and redirect policy.** `_validate_remote_url` requires http(s),
a hostname, no embedded credentials, and applies the `MCP_REMOTE` policy
(private network denied unless the literal `allow_private_network=True`); the
HTTP client disables redirects, ignores environment proxies, and re-validates
on every request to defeat DNS rebinding. Check a second HTTP path, a redirect
follower, a proxy env read, a truthy-but-not-`True` opt-in, and a resolved-IP
or error leak.

**Stdio launch.** The stdio allowlist, shell-metacharacter rejection, and
inline-code rejection are the boundary. A command outside the allowlist, an
operator env override that admits a shell, or a working-directory/argument
injection is a candidate; a user running their own local MCP server is not a
boundary violation.

**Server and tool identity confusion.** Responses, resources, elicitation
URLs, and tool calls must bind to the authenticated connection, request id, and
server identity, not to attacker-influenceable names or a reconnected server.
Check whether two servers can claim the same tool/resource identity, whether a
response can satisfy another server's pending call, and whether OAuth
protected-resource metadata is matched against the endpoint origin.

**Tool metadata as policy.** Descriptions, annotations, schemas, and completion
hints can guide the model but cannot grant capability. Find the deterministic
allowlist, server identity check, and handler authorization that remain
authoritative when metadata conflicts.

## Prompt and memory classes

**Role and provenance confusion.** `build_main_agent` uses
`event.message_str`; a plugin handler that returns a `ProviderRequest` replaces
the assembled prompt; `prompt_prefix`, selected prompt records,
`EXTRA_PROMPT.md`, workspace skills, `<system_reminder>` sender strings,
selected text, and message components each enter at a different trust level.
Check string concatenation, untyped history, caller-controlled role fields, and
a workspace-writable file that reaches `system_prompt`.

**Cross-session or cross-tenant context.** Conversation history, retrieval,
memory, and prompt caches must be keyed by the verified session and tenant.
Check a cache key that omits the account, a thread run that uses a parent
session without ownership, a memory read that mixes users, and a retrieval
filter that is applied after the query instead of inside it.

**Memory poisoning.** Attacker content or model summaries become durable memory
that later shapes another task, user, or privileged session. Review who may
create, update, merge, and delete memory; its provenance and scope; and whether
low-trust observations become durable instructions. Memory intentionally saved
by a user for that user's own requests is not a cross-boundary finding.

**Sensitive context extraction.** The assembled context contains credentials,
another user's data, or policy values that grant access, and user-influenced
output exposes them. Read prompt assembly and data fetch. Generic instructions
or behavior disclosure that crosses no data boundary is not a finding.

## Subagent and BTW classes

**Trust inheritance.** A subagent is an `Agent` plus a `HandoffTool` and
inherits the caller's `AuthContext`; every handoff requires `agent.manage`.
Check a subagent whose tool list is broader than the caller's authority, a
prompt record that adds tools, a background handoff that outlives revocation,
and a returned subagent result treated as trusted.

**Loop and route policy.** BTW work sessions and the conversation/work loop
routing are opt-in; `_loop_policy_error` re-applies read-only/route policy at
execution time because catalogs are snapshots. Check a stale snapshot that
allows a tool after the policy changed, a background task that never re-checks,
and a classifier failure that grants work authority.

## Universal moves

- Draw four maps: each execution identity, each capability, every writable
  context or memory source, and each output destination. Connect the principal
  at the start to the authority at the end.
- Start at side-effecting tools and walk backward through dispatcher, schema,
  confirmation, model context, retrieval, and ingestion. Start at durable
  memory reads and trace every writer.
- Compare direct, queued, retry, resume, batch, background, and delegated paths
  for the same action. The strongest gate must apply after arguments are final
  and before every side effect.

## Validation rules

1. Name the crossed boundary and observable result: attacker, affected
   principal or shared resource, execution identity, target, and unauthorized
   or unrequested action or disclosure.
2. For confused-deputy claims, prove the handler lacks requester-and-resource
   authorization and that the attacker cannot perform the same action normally.
   For action-binding claims, prove attacker content caused an action under the
   victim's authority that the victim did not intentionally request.
3. For memory or retrieval claims, cite both the attacker-controlled write and
   the later cross-principal read or privileged decision. A shared record with
   no reachable consumer is not enough.
4. For tool-schema claims, compare the normalized validated object with the
   object the handler uses. For MCP identity claims, verify the authenticated
   connection, request correlation, namespace, and effective credential.
5. For prompt-only claims without a code-level gate, keep the candidate as
   hardening or `needs_validation`. Never confirm a vulnerability from a
   persuasive-text argument alone.
6. Return `confirmed` only with a complete source trace and a meaningful
   result; `needs_validation` for one specific unresolved boundary fact and the
   bounded local or owner-observed check that resolves it.

---
outline: deep
---

# Skill reading and tool-catalog assembly

This page records current runtime behavior. Implemented clauses now live in [Architecture](/en/dev/architecture) and [Skills](/en/use/skills). Keep this page for the assembly formula, baseline table, and acceptance boundaries.

Related user docs: [Skills](/en/use/skills), [Computer Use](/en/use/computer), [Authorization](/en/use/authorization). Config fields: [AstrBot configuration](/en/dev/astrbot-config).

## Problem and current behavior

Skills are on-demand task manuals. Reading a manual does not require a host shell, and a Skill cannot grant extra privilege by declaring tools.

The runtime now closes the three former gaps:

1. **The tool catalog is computed from enabled Skills.** `SKILL.md` frontmatter parses `name`, `description`, and `tools:` once. Main-Agent assembly uses `assemble_tool_catalog()` over the four candidate layers, then intersects Persona three-state policy, visibility, and surface hard-strip. `agent_runner.config.misc.tool_schema_mode=skills_like` remains a two-stage light schema; it does not shrink the catalog.
2. **Manuals load through `read_skill`.** `build_skills_prompt()` requires `read_skill` and no longer mentions `cat` / `type`. The authorization action is low-risk `skill.read`. `computer_use_runtime=none` still injects the Skill inventory and says the agent cannot execute Shell or Python, but manuals remain readable.
3. **Social surfaces hard-strip high-risk tools from the catalog.** `_apply_local_env_tools` / `_apply_sandbox_tools` write runtime prompts only. IM, anonymous WebChat, plugins, agents, and API keys remove tools whose `required_actions` intersect `WEBCHAT_INSTANCE_TOOL_ACTIONS`. Authenticated WebChat keeps only the actions covered by the current step-up set.

## Current behavior

1. Keep multi-root discovery. The system prompt lists only Skill **names and short descriptions**.
2. Load manuals through a runtime tool `read_skill`, with paths locked inside the registered Skill directory. Computer Use is not required.
3. A Skill may declare needed **existing** tool names in frontmatter `tools:`. If several Skills declare the same tool, hang it once.
4. Compute the main-Agent tool catalog as an intersection. Do not dump the whole library and hide parameters with `skills_like`. Persona `tools is None` (use all) must not drop session-enabled plugin or MCP tools.
5. The binding table is a filter, not a grant. Social surfaces hard-strip instance-scoped high-risk tools using `WEBCHAT_INSTANCE_TOOL_ACTIONS`, even when a Skill lists `astrbot_execute_shell`. Do not use the full `HIGH_RISK_ACTIONS` set as a tool-catalog blacklist: that set also contains control-plane actions.

## Non-goals

Do not:

- Copy Claude Code `allowed-tools` pre-approval (`alwaysAllowRules`). On social IM that is Skill-granted shell.
- Copy Codex `$mention`, `skill://` URIs, `openai.yaml` / `SKILL.json`, or automatic MCP dependency install.
- Copy OpenCode's always-full tool pool. That product is a local developer CLI; AstrBot serves QQ, Telegram, and similar surfaces.
- Treat `skills_like` two-stage schemas as Skill binding. They hide parameters; they do not shrink the catalog.
- Add inline shell in Skill bodies, forked sub-agents, or glob-based auto-activation.
- Restore `platform_settings.group_wake_policy` or other removed surfaces.
- Reintroduce `CERT_NONE`, arbitrary filesystem reads, or a Dashboard HTTP proxy to load manuals.

If the user names a Skill, the host may inject `SKILL.md` into the current request as an optional optimization. That is not a public protocol.

## Comparison

| Concern             | Current AstrBot                                                                                                                            | Codex shape not to copy                        | This requirement                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | ------------------------------------------------------------------------------------- |
| Discovery           | Multi-root scan; inventory in the system prompt                                                                                            | Same                                           | Keep                                                                                  |
| Body load           | `read_skill`                                                                                                                               | `$mention` host inject or `skills.read`        | `read_skill` only; named inject is optional                                           |
| Paths               | `name` + relative path, locked to the registered directory                                                                                 | `package` + `skill://`, sandbox-aware          | `name` + relative path, locked to the registered directory                            |
| Tool declaration    | `SKILL.md` frontmatter `tools:`                                                                                                            | `openai.yaml` `dependencies.tools` (MCP-heavy) | `SKILL.md` frontmatter `tools:` with existing tool names                              |
| Declaration meaning | Filter, not authorization; `allowed-tools` is ignored                                                                                      | Prompt to install missing MCP                  | Filter, not authorization                                                             |
| Catalog             | Platform baseline ∪ session plugin/MCP ∪ Skill declarations ∪ on-demand computer tools, then ∩ Persona ∩ visibility filter ∩ surface strip | Built-in tools not filtered by Skill           | Same as current AstrBot                                                               |
| Social surface      | IM / anonymous WebChat / API keys: strip `WEBCHAT_INSTANCE_TOOL_ACTIONS` from the catalog                                                  | Local CLI permission model                     | Same as current AstrBot                                                               |
| Manual-read auth    | `skill.read`; works with `computer_use_runtime=none`                                                                                       | Dedicated `skills.read`                        | `skill.read` or an equivalent low-risk action; works with `computer_use_runtime=none` |

## Current anchors

Use these symbols. Do not add a parallel assembly path:

| Duty                    | Location                                                                                       |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| Skill inventory prompt  | `build_skills_prompt()` in `astrbot/core/skills/_skill_inventory.py`                           |
| Frontmatter parse       | `parse_skill_frontmatter()` in `astrbot/core/skills/_skill_frontmatter.py`                     |
| Request-scoped snapshot | `_skill_snapshot.py`; `_append_skills_prompt()` stores it on the event extra                   |
| Catalog assembly        | `assemble_tool_catalog()` in `astrbot/core/tool_catalog.py`                                    |
| Computer runtime prompt | `_apply_local_env_tools()`, `_apply_sandbox_tools()` write prompts only, and do not hang tools |
| Plugin/MCP filter       | Session plugin filtering inside `assemble_tool_catalog()`                                      |
| Execute-time auth       | `FunctionToolExecutor._authorize_execution()` in `astrbot/core/astr_agent_tool_exec.py`        |
| High-risk actions       | `HIGH_RISK_ACTIONS` (control plane + tools), `WEBCHAT_INSTANCE_TOOL_ACTIONS` (catalog strip)   |
| Two-stage schema        | `tool_schema_mode=skills_like` in `tool_loop_agent_runner.py`                                  |

## Current assembly

For each main-Agent request, the eight steps are normative. The formula is a summary; if it omits a clause, follow the steps and the baseline table.

1. Resolve the **enabled Skill set** with the current sources and priority: an empty Persona skill list disables all Skills, including workspace Skills; a named list filters local, plugin, and sandbox Skills; workspace Skills still inject when `computer_use_runtime=local` and the Persona has not disabled Skills. Source priority: [Skills](/en/use/skills).
2. Take the **candidate union** (see the baseline table): platform baseline ∪ session-enabled plugin/MCP tools that are not high-risk ∪ `tools:` from enabled Skills ∪ on-demand computer tools for this runtime. A Skill declaration may only add already-registered tool names. It cannot install MCP, open private-network MCP, or pull in a plugin tool that is not enabled for the session.
3. Dedupe. If several Skills declare the same tool, keep it once. Unknown tool names are ignored and logged.
4. Intersect with the Persona tool whitelist. Persona `tools is None` does not shrink this layer, so the step-2 union (including plugin/MCP tools) remains. An empty list means no ordinary tools (still keep `read_skill`; see the three-state table).
5. Intersect with session plugin filtering (keep MCP tools and tools with no plugin owner), then filter visibility by each tool's `required_actions` risk metadata and the request surface. Assembly does not call full `authorize()`.
6. **Hard-strip social surfaces**: remove every tool whose `required_actions` intersect `WEBCHAT_INSTANCE_TOOL_ACTIONS`. Current set: `tool.local_exec`, `tool.python_exec`, `tool.file_write`, `tool.browser_control`, `tool.mcp_write`, `tool.computer_use`. Strip by action intersection, not a tool-name blacklist. Remove them from the catalog for IM, anonymous WebChat, plugins, agents, and API keys. Do not only deny at execution. Authenticated Dashboard-driven WebChat keeps only actions covered by `webchat_step_up_actions`; a Skill cannot bypass step-up, and one stepped-up action does not unstrip the rest. Control-plane members of `HIGH_RISK_ACTIONS` such as `identity.operator.write` and `system.pip_install` must not appear in the main-Agent tool catalog anyway.
7. When `computer_use_runtime=none`, Shell, Python, and file-write tools stay out of the catalog even if a Skill declared them. `tool.file_read` is not in the hard-strip set; whether a social surface may see workspace file-read must be specified and tested separately. Default: hang it only for local/sandbox after Persona and visibility filters; a Skill declaration alone must not expose workspace file-read on IM.
8. `_apply_local_env_tools` / `_apply_sandbox_tools` expose the runtime capability list. The assembler adds computer tools from the intersection. Do not hang the full set unconditionally.

Formula (summary):

```text
candidates = platform_baseline ∪ session_plugin_mcp ∪ skill.tools ∪ on_demand_computer
catalog = surface_strip(
  visibility_filter(
    persona_whitelist ∩ candidates
  )
)
```

Keep `read_skill` according to the Persona three-state table (omit it when the Skill snapshot is empty). `skills_like` may remain a token optimization. It is orthogonal to catalog computation.

Catalog computation is one pure function, `assemble_tool_catalog(...)` in `astrbot/core/tool_catalog.py`. Inputs: the frozen Skill snapshot, Persona three-state policy, request surface, `computer_use_runtime`, session plugin filter, and the registered-tool table. Output: a tool-name set, then one materialized `ToolSet`. Tools already present on the request are reattached only after the same surface strip.

### Baseline and candidate layers

Persona `tools is None` (“use all”) means “do not shrink the four layers below”. It does not mean “drop plugin tools unless a Skill named them”. A Skill with no `tools:` field only supplies a manual: it adds no tools and does not remove other layers.

| Layer                    | Enters the candidate set when                                                                     | Examples                                                                                                                                                                                        | Depends on Skill `tools:`?                                         |
| ------------------------ | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Platform baseline        | The matching capability is on                                                                     | Memory search (`search_memory` and siblings), proactive messaging, enabled web search, group history (when configured), `read_skill` (when Skills are enabled or kept by the three-state table) | No                                                                 |
| Session plugin / MCP     | The plugin is active and passes session plugin filtering; MCP tools with no plugin owner are kept | User plugin tools, MCP read tools                                                                                                                                                               | No. A Skill cannot install MCP or open private-network MCP         |
| Skill declarations       | Enabled Skill frontmatter `tools:`                                                                | A retrieval Skill listing `search_memory`                                                                                                                                                       | Yes. Filter existing names only                                    |
| On-demand computer tools | `computer_use_runtime` is `local` or `sandbox`, after Persona and hard-strip                      | Shell, Python, file write, Neo lifecycle tools, browser (when sandbox capabilities allow)                                                                                                       | May declare, cannot grant. This layer is empty when `runtime=none` |

Neo lifecycle tools (`astrbot_create_skill_payload` and siblings) belong to the sandbox + `shipyard_neo` on-demand computer layer. They are not platform baseline and must not be hung unconditionally.

### Implementation constraint: visibility versus authorization

The `visibility_filter` term above must not call the full asynchronous `authorize()` during assembly. Assembly may use only static, predictable visibility inputs:

1. Collect the four candidate layers, the Persona's three-state policy, and the request surface.
2. Filter by runtime capability, plugin selection, each tool's `required_actions` risk metadata, and the request surface.
3. Materialize one `ToolSet`; execution must still pass through `FunctionToolExecutor._authorize_execution()`.

This preserves request-scoped controls such as WebChat step-up without making catalog contents depend on an authorization call at the wrong lifecycle point. Social surfaces hard-strip by intersection with `WEBCHAT_INSTANCE_TOOL_ACTIONS`, not a tool-name blacklist and not the full `HIGH_RISK_ACTIONS` set.

### Three-state Persona tool policy

The implementation must pin the difference between `None`, an empty list, and a non-empty list:

| Persona `tools`  | Ordinary tools                                                                                                                | `read_skill`                                      |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `None` (use all) | Do not shrink the four candidate layers (platform baseline, session plugin/MCP, Skill declarations, on-demand computer tools) | Keep                                              |
| `[]` (use none)  | Remove all                                                                                                                    | Keep, but only for Skills enabled in this request |
| Non-empty list   | Intersect with the list                                                                                                       | Keep, even if the list does not name this tool    |

`read_skill` is a system-reserved low-risk read capability. It does not grant a Persona or Skill permission to use any other tool.

### Request-scoped Skill snapshot

`read_skill` must use a Skill snapshot frozen when the request is built; it must not rescan the global Skill directories by name. The snapshot should contain at least the Skill name, source, resolved Skill root, runtime-copy location, an identity such as a content digest, and frozen copies of regular files under a host-readable Skill directory. During one tool loop, disabling, replacing, syncing, or retargeting a symlink must not make the prompt and the object read by `read_skill` disagree. Host freeze reads cap each file at 64 KiB and the tree at 256 KiB / 32 files; overflow stays out of the snapshot. `SKILL.md` and referenced files are served from that snapshot, not reopened from disk. Sandbox copies still use the remote path locked at request time.

After same-name source precedence is resolved, only the selected source remains addressable. `read_skill(name=...)` must not guess between sources. Sandbox cache paths must also be checked against the current session sandbox root; a cached path string is not trusted by itself.

## `read_skill`

The built-in tool registration name and the model-facing name are both `read_skill`. Do not reuse `astrbot_file_read_tool` or the shell.

### Input

| Field  | Constraint                                                                 |
| ------ | -------------------------------------------------------------------------- |
| `name` | Required. Must be a name in this request's enabled Skill set.              |
| `path` | Optional, default `SKILL.md`. POSIX path relative to that Skill directory. |

### Resolve and reject

Resolve against `skill_dir`. Reject:

- `..`, absolute paths, drive letters, UNC, extra leading `/`
- a resolved path that leaves that Skill directory
- directories, symlink escapes, non-regular files
- a `name` not in the enabled set
- empty names and control characters

Open only the registered Skill's `SKILL.md` and files under that directory. Do not enter other workspace paths or the `data/` root.

In sandbox runtime, read the resolvable sandbox copy. In local runtime, read the local or workspace copy. Tool results should return a path relative to the Skill directory, or a fixed placeholder, never a host absolute path.

Path validation must not be only a non-atomic `resolve()` followed by `read_text()`: a symlink replacement can create a TOCTOU escape. Freeze and read must not follow symlinks. Unix opens through directory handles with `O_NOFOLLOW`; Windows walks path parts without following links. If an opened fd can be resolved to a real path, that path is authoritative. If it cannot, Unix fails closed instead of accepting the intended path.

### Output and limits

Return UTF-8 text. Per-file cap: 64 KiB, truncated with a note that tells the model to pass a relative `path` for referenced files. Referenced files use the same directory lock. Do not enumerate the whole Skill tree in one call. The system prompt may say relative paths are relative to that Skill directory. Omit `read_skill` from the catalog when the Skill snapshot is empty.

### Authorization

Use a dedicated low-risk `skill.read` action and register it in `ACTIONS`, role grants, resource-type mapping, authorization docs, and tests. Do not reuse `session.read` merely to avoid one registry entry: the tool execution boundary currently authorizes a `Resource(type="tool", ...)`, which has different semantics. Do not classify `read_skill` as `tool.local_exec` or `tool.file_read`.

When `computer_use_runtime=none`, `read_skill` still belongs in the catalog. Memory and retrieval Skills work without Computer Use.

Scripts, shell, and file writes still use the original high-risk tools. Authorization does not change.

### System prompt

Delete the rule that requires a runtime-shell-compatible `cat` / `type`. Replace it with: call `read_skill` when a Skill matches; pass a relative `path` for referenced files. When `runtime=none`, keep the “cannot execute shell / Python” note, but do not forbid reading the manual.

## Frontmatter `tools:`

Add an optional `tools` field to the existing YAML frontmatter.

```markdown
---
name: search-notes
description: Search user notes and quote the original text.
tools:
  - search_memory
---
```

Rules:

- Values are registered AstrBot tool names, such as `astrbot_execute_shell` or `search_memory`. Parse registered names; do not accept model-facing aliases.
- Do not list `read_skill` in `tools:`. It is kept by the Persona three-state table, not by declaration.
- Only `tools:` is recognized. Do not read `allowed-tools` or other Claude / Codex aliases, and do not import `Bash(gh:*)` pattern language. Semantics: **filter, not pre-approval**. The Agent Skills spec marks `allowed-tools` as experimental pre-approval; this repository does not implement or map that field. User docs must say community manuals that only set `allowed-tools` are ignored and do not gain privilege.
- Unknown tool names are ignored and logged. Do not fail the whole Skill.
- Missing `tools:` means the Skill **adds no extra tools**. Baseline tools remain. Do not treat omission as “the full tool pool”.
- Do not add `SKILL.json` / `openai.yaml`. MCP stays on the existing MCP server config. A Skill cannot install MCP or open private-network MCP.

Parse frontmatter once into structured metadata (name, description, declared tools, and parse warnings), rather than loading each field independently. `tools` must be a string list with deduplication and bounds on item length and total count. Unknown tools are logged and ignored. Plugin, Workspace, and Sandbox-cache Skills must use the same parser; `tools:` cannot work only for local Skills.

Skill bodies and descriptions are potentially untrusted data. `read_skill` results should carry structured Skill name and relative path boundaries and state that body text does not increase authority. Do not treat instructions inside a body as an authorization policy.

## Authorization and surfaces

Execution still goes through `FunctionToolExecutor._authorize_execution`. Skills affect **catalog visibility** only.

Hard constraints:

- Dashboard bind defaults to `127.0.0.1`. Non-loopback is a deployment choice.
- IM, anonymous WebChat, plugins, agents, and API keys do not inherit Dashboard roles.
- The six WebChat instance-scoped high-risk actions still require `/authorization/webchat-step-up` in the current session/config.
- Even if a Skill lists `astrbot_execute_shell`, the matching tool does not appear on a social-surface catalog.
- After a successful WebChat step-up, an authenticated Dashboard WebChat catalog may include tools mapped to `WEBCHAT_INSTANCE_TOOL_ACTIONS`. IM and API keys never do.
- User-facing failures stay generic. Do not echo host paths or authorization details.

## Delivery slices

Slice 1 and slice 2 are current behavior. Do not add a parallel assembly path.

### Slice 1: Unbind manual reads from the shell

- `read_skill` uses a locked path and low-risk `skill.read` authorization.
- A request-scoped Skill snapshot is shared by the prompt and `read_skill`.
- `build_skills_prompt()` no longer mentions `cat` / `type`.
- `read_skill` stays in the catalog when `runtime=none`.
- Regression: a memory Skill can read `SKILL.md` without Computer Use; `../` and absolute paths fail.

### Slice 2: Declaration filter and hard strip

- Parse frontmatter `tools:`.
- Build a pure candidate-tool set first, then materialize one `ToolSet`; `_apply_local_env_tools` / `_apply_sandbox_tools` write runtime prompts and do not unconditionally mutate the request catalog.
- `assemble_tool_catalog` computes the catalog from the eight steps and the baseline table. Add computer tools on demand; do not hang the full set.
- Hard-strip `WEBCHAT_INSTANCE_TOOL_ACTIONS` on social surfaces, including MCP write tools. Authenticated WebChat keeps only the stepped-up action intersection.
- Regression: two Skills declaring the same tool yield one catalog entry; IM cannot see Shell; WebChat step-up is not bypassed by a Skill; an empty Persona skill list still disables workspace Skills; Persona `tools is None` still keeps undeclared plugin tools.

### Explicitly out of slice 3

Host auto-inject of `SKILL.md` when the user names a Skill, paginated `skills.list`, and MCP dependency install are out of scope.

## Acceptance

These behaviors are covered by `tests/unit/test_skill_tool_assembly.py` and main-Agent catalog tests:

1. The system prompt lists enabled Skill names and descriptions and does not require `cat` / `type`.
2. `read_skill` opens only files under an enabled Skill directory. `../etc/passwd`, absolute paths, and other Skill directories fail.
3. With `computer_use_runtime=none`, `read_skill` is available and Shell / Python / file-write tools are absent.
4. `tools:` from enabled Skills enter the candidate set and appear after Persona intersection. Undeclared platform-baseline and session plugin/MCP tools remain when Persona `tools is None`. An empty Persona list removes them and keeps only `read_skill`.
5. Two Skills that declare the same tool hang it once.
6. A social surface (not a WebChat step-up subject) catalog contains no tool whose `required_actions` intersect `WEBCHAT_INSTANCE_TOOL_ACTIONS`.
7. A Skill frontmatter listing `astrbot_execute_shell` does not let an IM subject pass `tool.local_exec`. `tool.file_read` is not hard-stripped; after Persona and visibility filters, workspace file-read may appear on IM for local/sandbox runtimes, but a Skill declaration alone must not hang it.
8. `skills_like` still only changes schema shape, not the catalog set above.
9. Replacing or disabling a Skill after request creation does not change that request's `read_skill` snapshot.
10. The `persona.tools` matrix covers `None`, `[]`, and non-empty lists; an empty list keeps `read_skill` and removes other tools as specified.
11. Same-name precedence, Sandbox cache paths, and symlink changes cannot cause cross-source reads or directory escape.
12. When Persona `tools is None`, an enabled plugin tool that no Skill listed in `tools:` still appears in the catalog.
13. After a successful authenticated WebChat step-up, the catalog may include high-risk computer tools. IM and API keys never do.
14. After `read_skill` opens a file, the real path is still under the snapshot root (`O_NOFOLLOW` or equivalent).
15. Sandbox + `shipyard_neo` lifecycle tools are on-demand computer tools and are absent when `runtime=none`.
16. A Skill that only sets `allowed-tools` and omits `tools:` adds no tools and grants no privilege.
17. Existing request tools are re-ingested through the same assembly rules; a Persona empty list or social-surface strip cannot be bypassed by preloaded high-risk tools.

## Docs and config sync

Current docs already match:

- [Skills](/en/use/skills) documents the load steps, Local runtime notes, and the rule that only `tools:` is recognized, `allowed-tools` is ignored, and a declaration does not grant privilege.
- This page records the assembly formula and acceptance boundaries. Implemented clauses also live in [Architecture](/en/dev/architecture).
- `skill.read` is registered in authorization docs and `astrbot/core/auth/registry.py`.
- Keep this page structurally aligned with the Chinese [Skills 读取与工具目录装配](/dev/skill-tool-assembly).
- Do not point at `docs.astrbot.app`.

# AstrBot Configuration Reference

AstrBot configuration evolves with Providers, platform adapters, and Agent capabilities. This page documents the current stable groups, defaults, and operational boundaries instead of maintaining a hand-copied “complete default configuration.”

The authoritative code is:

- defaults: `DEFAULT_CONFIG` in `astrbot/core/config/default.py`;
- WebUI field metadata: `CONFIG_METADATA_3` and `CONFIG_METADATA_3_SYSTEM` in the same file;
- loading, integrity checks, and password migration: `astrbot/core/config/astrbot_config.py`.

## File locations and loading behavior

The default profile is stored at `data/cmd_config.json` under the runtime root. With `ASTRBOT_ROOT` set, it becomes `$ASTRBOT_ROOT/data/cmd_config.json`.

Additional profiles created in the WebUI are stored as `data/config/abconf_<uuid>.json`. Profile-to-message-session bindings are maintained by the configuration manager; do not move a binding by renaming files.

The files are parsed with Python's standard JSON parser and must therefore be **strict JSON**:

- use `true` and `false` for booleans;
- do not add comments;
- do not use trailing commas;
- quote keys and strings with double quotes.

At startup, AstrBot recursively inserts missing current defaults, fixes key order, and removes unknown keys that are not present in the current default structure. Adding an unsupported field manually does not extend the configuration model.

> [!TIP]
> Prefer the WebUI: profile settings are under **Config**, model and Provider records under **Providers**, adapter instances under **Platforms**, and process-wide settings are grouped under **Settings**. If you edit JSON directly, keep a copy and restart AstrBot afterward.

## Top-level structure

| Key                                               | Purpose                                                                                                                                                                                                                                                         |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config_version`                                  | Current core configuration version, default `4`. Do not downgrade it manually.                                                                                                                                                                                  |
| `platform_settings`                               | Cross-platform receive, send, rate-limit, and segmented-reply behavior.                                                                                                                                                                                         |
| `provider_sources`                                | Provider endpoints and credentials, maintained by the Providers page.                                                                                                                                                                                           |
| `provider`                                        | Concrete chat, STT, TTS, embedding, rerank, and other model instances.                                                                                                                                                                                          |
| `agent_runner`                                    | Agent Runner type and inline configuration for this profile.                                                                                                                                                                                                    |
| `provider_settings`                               | Shared AI switch, retrieval, streaming, and Computer Use behavior for this profile.                                                                                                                                                                             |
| `subagent_orchestrator`                           | SubAgent handoff orchestration.                                                                                                                                                                                                                                 |
| `provider_stt_settings` / `provider_tts_settings` | Default speech-to-text and text-to-speech models and switches.                                                                                                                                                                                                  |
| `provider_ltm_settings`                           | [Group chat context awareness](../use/group-chat-context) (in-memory group context, image captions, persisted group history). The JSON key is still historical; it is not the Alkaid long-term-memory switch. Random group proactive replies have been removed. |
| `content_safety`                                  | Built-in keyword checks and optional external content-safety checks.                                                                                                                                                                                            |
| `dashboard`                                       | WebUI listening, authentication, rate limiting, and TLS; Dashboard account identity and authoritative TOTP state live in its database.                                                                                                                          |
| `platform` / `platform_specific`                  | Adapter instances and platform-specific behavior for Lark, Telegram, Discord, and others.                                                                                                                                                                       |
| `command_prefixes`                                | Command framing prefixes; default `["/"]`.                                                                                                                                                                                                                      |
| `llm_access`                                      | Per-profile LLM access policy for direct and group messages; defaults to `private=prefix`, `group=prefix`, `prefixes=["/"]`.                                                                                                                                    |
| `admission`                                       | Unlisted session and sender policy; defaults `unlisted_sessions=allow` and `unlisted_senders=allow`.                                                                                                                                                            |
| `inbound_coalesce`                                | Optional bounded merging of consecutive private-message LLM fragments; disabled by default.                                                                                                                                                                     |
| Other top-level keys                              | Administrators, T2I, proxy, logging, timezone, plugins, knowledge base, Trace, and metrics.                                                                                                                                                                     |

Object layouts inside `provider_sources`, `provider`, and `platform` come from the currently registered type templates. Do not copy old objects from documentation. Create them in the WebUI and inspect the saved result if necessary. A model references its source through `provider_source_id`; use the WebUI when renaming or deleting a source so references are updated together.

## Inbound routing

User-facing steps are in [When the bot replies in groups](../use/group-wake). `command_prefixes` and `llm_access` are read from the configuration profile selected for the event. `command_prefixes` only frames command headers; it is never combined with an LLM prefix. Each `llm_access.prefixes` entry is the complete string users type, uses token-boundary matching, and follows longest-match semantics. Non-empty LLM prefixes reserve their first command-root token in the same profile, so a prefix that conflicts with an enabled command is rejected by the Dashboard.

| Key                                  | Values                    | Meaning                                                                                                                            |
| ------------------------------------ | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `llm_access.private`                 | `open` / `prefix` / `off` | Default `prefix`. Direct messages always pass, require an LLM prefix, or never open a new LLM turn. A continuation may still pass. |
| `llm_access.group`                   | `open` / `prefix` / `off` | Base gate for group LLM access. Mentions are not a gate; saved `mention` / `prefix_or_mention` fall back to `prefix` at runtime.   |
| `llm_access.reply_to_bot`            | `true` / `false`          | Adds replying to the bot as an explicit OR condition for group LLM access.                                                         |
| `inbound_coalesce.enable`            | `true` / `false`          | Enables the bounded turn window; disabled by default. The current implementation coalesces private messages only.                  |
| `inbound_coalesce.wait_seconds`      | Number                    | Quiet-period delay before a buffered turn is flushed.                                                                              |
| `inbound_coalesce.max_total_seconds` | Number                    | Maximum lifetime of a buffered turn, regardless of new fragments.                                                                  |
| `inbound_coalesce.max_typing_wait`   | Number                    | Guard that resumes a paused turn when a typing-stop notice is lost.                                                                |

Routing checks commands before LLM access. A matched command wins; a bare command group emits help; an unknown subcommand emits the Orbit diagnostic and never falls through to the LLM. Otherwise the event either passes the LLM gate or is dropped. Notices and requests are passthrough events. When coalescing is enabled, later private fragments continue an open turn without repeating the LLM prefix, while a command discards the buffered turn. NapCat `input_status` notices stay out of the message pipeline and only pause or resume the turn window.

Unlisted sessions are controlled by top-level `admission.unlisted_sessions`, default `allow`. `deny` admits groups or DMs that already have an overlay on the canonical session key, or that this profile listed during upgrade. Unlisted senders are controlled by `admission.unlisted_senders`, also default `allow`. `deny` admits only IM subjects that already have a `blocked` or `llm_enabled` overlay. Write those overlays with `/user block`, `/user unblock`, `/user llm on|off`, or the Sender target on Dashboard [custom rules](../use/custom-rules). WebChat, OneBot `notice` / `request`, and senders with `provider.manage` on the current instance skip this gate. `id_whitelist`, `enable_id_white_list`, and `wl_ignore_admin_*` are gone.

## `platform_settings`

| Key                                       | Default                                | Meaning                                                                                                                                                |
| ----------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `unique_session`                          | `false`                                | Split separate sessions for members inside a group.                                                                                                    |
| `group_sender_concurrency`                | `false`                                | Experimental. Different group senders may generate in parallel; a whole turn still sends one-at-a-time per group. Ignored when `unique_session` is on. |
| `rate_limit`                              | `60` seconds / `30` messages / `stall` | Wait (`stall`) or discard (`discard`) when the limit is exceeded.                                                                                      |
| `reply_prefix`                            | `""`                                   | Prefix added to replies.                                                                                                                               |
| `reply_with_mention` / `reply_with_quote` | `false`                                | Mention the sender or quote the source message when supported by the adapter.                                                                          |
| `forward_threshold`                       | `1500`                                 | Long-reply forwarding threshold for the OneBot `aiocqhttp` adapter; support on other platforms depends on the adapter.                                 |
| `segmented_reply`                         | See current defaults                   | Non-streaming segmentation, timing, and cleanup rules.                                                                                                 |
| `path_mapping`                            | `[]`                                   | Map paths from a platform container into paths AstrBot can read, using `source:target`. This is still used by the receive/respond pipeline.            |
| `ignore_bot_self_message`                 | `false`                                | Ignore the bot's own messages. `ignore_at_all` is still persisted, but it is not an LLM gate.                                                          |

Example path mapping:

```json
{
  "platform_settings": {
    "path_mapping": [
      "/app/.config/QQ:/var/lib/docker/volumes/napcat_data/_data"
    ]
  }
}
```

This is a partial illustration and must not replace the complete file. Because Windows drive letters contain a colon, configure mappings in the WebUI and validate them against real platform events.

## `agent_runner`

This is the profile AI execution object: `{ "runner_type": "local"|"dify"|"coze"|"dashscope"|"deerflow", "config": {...} }`. Chat model, Persona, compression, and step caps live here. Do not put them back under `provider_settings`.

### Model selection and retries

- `agent_runner.config.model.provider_id` selects the local Agent's default chat model.
- `agent_runner.config.model.fallback_provider_ids` lists chat-model IDs tried in order after the primary model fails.
- `agent_runner.config.model.request_max_retries` is the per-model maximum retry count and defaults to `5`. Fallback and retries are separate layers.

### Persona

- Local runner: `agent_runner.config.persona.persona_id`.
- Third-party runners: `agent_runner.config.persona_id`.
- Safety mode: `agent_runner.config.persona.safety_mode`.

See [Personas](../use/persona) for selection priority and permission semantics.

### Context compression

These fields live under `agent_runner.config.compression`:

| Key                   | Default                         | Meaning                                                                       |
| --------------------- | ------------------------------- | ----------------------------------------------------------------------------- |
| `overflow_strategy`   | `llm_compress`                  | `llm_compress` or `truncate_by_turns`.                                        |
| `keep_recent_ratio`   | `0.15`                          | Exact recent-context token ratio, clamped to `0`–`0.3`.                       |
| `provider_id`         | `""`                            | Empty means the chat model active for the current session.                    |
| `instruction`         | Built-in five-point instruction | Summary prompt.                                                               |
| `max_turns`           | `-1`                            | Conversation turns kept before compression; `-1` disables this turn limit.    |
| `trim_turns`          | `1`                             | Turns removed per turn-based truncation pass.                                 |
| `fallback_max_tokens` | Runtime default `128000`        | Fallback window when neither model config nor built-in metadata supplies one. |

See [Automatic Context Compression](../use/context-compress) for the full behavior.

### Steps, tools, and proxy

- `agent_runner.runner_type` selects the built-in `local` Agent or Dify, Coze, DashScope, or DeerFlow. Third-party keys and app IDs live in `agent_runner.config`.
- `agent_runner.config.misc.max_steps` is the local Agent step cap, default `128`, and also applies to current SubAgent executions. Stored `30` values upgrade once when `config_version` advances to `4`.
- `agent_runner.config.max_steps` is the third-party runner step cap, default `128`.
- `agent_runner.config.misc.tool_call_timeout` is the per-tool timeout in seconds, default `120`.
- `agent_runner.config.misc.tool_schema_mode` uses `full` schemas or the lighter two-stage `skills_like` mode. `skills_like` hides parameters; it does not shrink the tool catalog.
- `agent_runner.config.misc.sanitize_context_by_modalities` removes unsupported modalities and tool structures according to the current model, changing the history seen by that model.
- `agent_runner.config.proxy_mode` / `proxy_url` control third-party outbound proxies: `inherit` follows the global proxy, `direct` connects without environment proxies, and `custom` uses only `proxy_url`.

## `provider_settings`

### Provider selection and retries

- `enable` enables AI Provider processing and defaults to `true`.
- `provider_pool` limits Providers available to this profile; `["*"]` means all.
- `default_image_caption_provider_id` and `image_caption_prompt` caption images in the current main-agent request and quoted messages. They are not affected by group-history caption limits.
- `provider_ltm_settings.image_caption_*` applies only to [group chat context awareness](../use/group-chat-context) history captions. `image_caption_scope` is `all`, `allowlist`, or `denylist`; `image_caption_groups` accepts full UMOs only; `image_caption_min_interval` and `image_caption_max_concurrency` bound interval and global concurrency. `image_caption_cache_ttl` defaults to `0` (off) and is scoped by UMO plus content id. `image_caption_lazy` defaults to off.
- Group-chat JSON cards enter group context and are used as a `[Shared Card]` summary when an ordinary LLM request has no text prompt.

API keys are sensitive configuration. Never commit a real `cmd_config.json`, screenshots, logs, or backups. Logs and Trace data can also contain Provider IDs, request errors, and tool output.

### Persona, prompts, and sessions

- `persona_pool` limits selectable Personas; `["*"]` means all.
- `prompt_prefix` is the user-prompt template. Placeholders use logic-free `{{name}}` syntax, not Jinja2. The only allowed key is `prompt`. If the template contains `{{prompt}}`, that slot is replaced with the user input; if it does not, the prefix is prepended. Persona `system_prompt` and workspace `EXTRA_PROMPT.md` are not templates.
- Built-in LLM templates use the same `{{name}}` syntax. Cron wake allows `cron_job`; background-task wake allows `background_task_result`; tool-loop notices allow `follow_up_lines`, `tool_names`, `tool_name`, `streak`, `overflow_path`, and `read_tool_hint`. Unknown `{{name}}` tokens stay literal, and substitution values are not scanned again.
- `identifier` and `group_name_display` append a persistent user `<system_reminder>` with user identity or group name after this turn's last user message.
- `datetime_system_prompt` appends a temporary current-time `<system_reminder>` after this turn's last user message. It is not saved to conversation history and is not written into the system prompt.

The default Persona ID is configured on `agent_runner`. See [Personas](../use/persona) for selection priority.

### Tool display

- `show_tool_use_status` / `show_tool_call_result` expose tool state and a result preview to users.
- `buffer_intermediate_messages` combines intermediate text during non-streaming multi-step runs.
- `proactive_capability.add_cron_tools` exposes proactive/Cron tools to the local Agent.

### Streaming

- `streaming_response` enables Provider streaming.
- `unsupported_streaming_strategy` uses `realtime_segmenting` on platforms without native streaming or `turn_off` to disable streaming for that response.
- Session `/flow enable|disable|unset|status` can override the global value. Priority is `event.extra["enable_streaming"]` > session override > `provider_settings.streaming_response`. The effective value is pinned when a request starts.

The old `provider_settings.streaming_segmented` field has been removed. Do not add it back.

### Computer Use and sandboxing

- `computer_use_runtime` is `none`, `local`, or `sandbox` and defaults to `none`.
- `computer_use_require_admin` is no longer a runtime authorization switch. Computer capabilities use the unified `tool.computer_use`, `tool.local_exec`, `tool.file_read`, and `tool.file_write` actions. WebChat still requires step-up for instance tools; IM skips step-up when the sender is bound as `instance_operator` on that config.
- `sandbox.booter` selects `shipyard_neo` or `cua`; related fields store endpoint, token, profile, TTL, or CUA OS, telemetry, and local/cloud settings.

Local mode operates directly on the AstrBot host and belongs only in a trusted environment. A sandbox is not an authorization boundary by itself; continue to restrict administrators, Persona tools, and external network access.

### Search and images

`web_search`, `websearch_provider`, and provider-specific keys configure built-in web search; `web_search_link` controls link output. Enter keys through the WebUI.

`image_compress_enabled` and `image_compress_options.max_size/quality` control image handling in the request-preparation choke point `prepare_provider_request`. The main-agent chat path, SDK `llm_generate`, and `tool_loop_agent` share that step. Provider-bound images are converted to JPEG there; the long edge is downscaled only and never upscaled. Each prepared JPEG is strictly smaller than 512 KiB (524,288 bytes) before Base64 encoding. Originals larger than 64 MiB are skipped before decoding. Animated GIF/WebP sources are dhash-sampled, at most 8 frames. Disabling compression still converts to JPEG without the configured long-edge resize, but the 512 KiB cap can still shrink the image. When Computer Use runs in the CUA sandbox (`computer_use_runtime=sandbox` and `sandbox.booter=cua`), stills skip the configured resize so pixel coordinates stay 1:1 unless the 512 KiB cap requires a further reduction; images larger than 5 MB without resize still warn, and images above the 20 MB preparation cap are dropped. The main agent only materializes adapter refs to local paths and does not pre-encode chat attachments to JPEG. `max_quoted_fallback_images` and `quoted_message_parser` limit quoted and forwarded-message expansion to prevent unbounded fetching. For `quoted_message_parser`, `0` is a valid boundary: depth limits keep the root level but stop child recursion, and `max_forward_fetch=0` disables recursive `get_forward_msg` calls. Negative or invalid values fall back to defaults; this setting does not globally disable a direct quoted-message `get_msg` fallback.

## BTW model selection

When `btw.enabled` is enabled for a local Agent profile, `btw.conversation_loop.provider_id` and `btw.work_loop.provider_id` select the chat model for each loop. A configured loop model takes priority over the event/session model selection. An empty field preserves the current selection, including the profile default. Messages without an explicit work-loop marker use the conversation model. Disabling BTW ignores both overrides.

The selected provider must still be a configured chat model. An unavailable or incompatible loop provider falls back to the event/session model selection and logs a warning, so one stale setting cannot strand every request; it never silently switches to the other loop's model. Only the chat model falls back: the work loop's Computer Use runtime, read-only constraint, and tool catalog stay governed by their own fields. Existing model fallback and retry settings continue to apply to the selected primary provider.

### Computer Use boundaries

With BTW enabled, the conversation loop runs with Computer Use set to `none`, including handoffs and explicitly supplied tools. Host shell, Python, filesystem, browser, CUA, and sandbox Skill lifecycle tools stay outside its tool catalog. Ordinary Skill manuals remain available through `read_skill`.

`btw.work_loop.computer_use_runtime` accepts `inherit` (default), `none`, `local`, or `sandbox`. `inherit` uses `provider_settings.computer_use_runtime`. The effective runtime applies to the work request and its handoffs; `none` excludes computer tools even when they were explicitly declared. Disabling BTW preserves the existing Computer Use configuration. These settings select capabilities; they do not grant roles or bypass authorization, WebChat step-up, path restrictions, or sandbox checks.

## BTW loop conversation history and work hand-off

With BTW enabled, the two loops keep separate conversation histories. The conversation loop uses the session's current conversation; the work loop owns a second conversation under the same session, created on its first task, and both appear in the session's conversation list and the Dashboard. Because the histories are independent, a delayed work reply never overwrites a chat turn, and the reverse holds too.

The work loop never reads its own history: every work task starts from an empty history. The conversation loop hands the task over explicitly by calling the `submit_work_task` tool with a self-contained task prompt. The tool returns immediately, the task runs in the background, and its result is still delivered to the user through the result-decoration and send stages. The tool is offered only when BTW and the work loop are enabled and the current run is the conversation loop; the work loop never receives it. The prompt must carry every needed detail, because the work loop cannot see the chat.

The conversation loop can read the work loop's history: its request context carries the work loop's most recent complete turns as provider-only context that is never written into either history, so the chat can refer to what the work loop produced. Hand-off reduces turns to their text roles, so tool calls and their results never cross the loop boundary. Disabling BTW leaves a run reading only its own conversation's history, creating no work conversation and injecting nothing.

## BTW plugin tool assignments

When BTW is enabled in a configuration profile, **More Features → BTW Dual Loop → Plugin tool loop assignments** assigns each enabled non-system plugin's LLM tools to conversation, work, or both loops. An unassigned plugin defaults to work. Selecting both saves an explicit override; selecting work again removes it. Disabling BTW preserves normal tool availability.

The main Agent and its subagent handoffs apply the same assignment, together with existing Persona, profile, and authorization restrictions. An assignment never grants permission to execute a tool. Plugin event handlers and explicit commands keep their existing execution path; this setting does not turn an entire plugin into a background task.

## BTW MCP tool assignments

With BTW enabled, **MCP server loop assignments** selects conversation, work, or both for every enabled MCP server. All tools from that server share the assignment in the main Agent and subagent handoffs. Servers without an override default to work; selecting both saves an explicit override, and selecting work removes it. Disabling BTW preserves ordinary MCP tool availability.

Assignments are saved per configuration profile. They control tool visibility and do not replace MCP read/write authorization or the existing connection, private-network, and redirect restrictions.

## BTW Skill visibility

With BTW enabled, **Skill loop assignments** chooses conversation, work, or both for each enabled ordinary Skill. Ordinary Skills default to both loops; choosing one loop saves an override, and choosing both removes it. Workspace Skills are available only to the work loop with the `local` runtime. Disabling BTW preserves the standard Skill selection path.

Loop assignments narrow the enabled Skills before the request's Skill snapshot is frozen. The prompt, `read_skill`, and Skill-declared tool candidates therefore use the same selection. Persona and plugin restrictions still apply, including an empty Persona Skill list. A loop assignment never grants execution permission: `read_skill` can read permitted Skill manuals when Computer Use is `none`, while Shell and Python remain unavailable.

## SubAgents, speech, and knowledge base

- `subagent_orchestrator.main_enable` enables handoffs.
- `remove_main_duplicate_tools` removes only tools that overlap between the main Agent and SubAgents; it defaults to `false`.
- `router_system_prompt` and `agents` define routing and SubAgents. Maintain them through the dedicated page; see [SubAgent Orchestration](../use/subagent).
- `provider_stt_settings` controls STT and its default model.
- `provider_tts_settings` controls the TTS model, dual output, file service, and a `0`–`1` trigger probability.
- `kb_names`, `kb_fusion_top_k`, and `kb_final_top_k` select default knowledge bases and retrieval counts.
- `kb_agentic_mode` exposes knowledge-base retrieval as a model-controlled tool.

Alkaid [Long-term Memory](../use/long-term-memory) currently has no enable/disable configuration. Do not treat `provider_ltm_settings` as its switch. For recent group-message injection, see [Group Chat Context Awareness](../use/group-chat-context).

## BTW conversation entry

`btw.enabled` defaults to `false`. Enabling it sends ordinary admitted AI requests through the conversation loop and the existing Agent executor. It does not bypass message admission, session AI switches, or plugin request handling. With BTW disabled, the pipeline directly uses the current Agent request path and retains its capabilities.

Automatic classifier candidates are evaluated separately. Enabling this entry does not select an automatic routing strategy.

The work executor additionally requires `btw.work_loop.enabled`, also `false` by default. It reuses the Agent executor and records pending, running, completed, failed, and cancelled task states. `btw.work_loop.max_concurrent` limits active execution (default `2`); it does not impose a waiting-queue length limit. `btw.work_session.max_age_seconds` retains terminal states for `3600` seconds by default; active tasks do not expire, and expired terminal records are removed during the next session operation. Runtime-owned background services perform task execution and cleanup when attached by the scheduler.

Detached work acknowledges receipt before execution and returns results through the current response-decoration and delivery stages, including reply content checks. Inbound stages are not rerun. WebChat keeps the original request identifier open through the final result; acknowledgement does not end the request. Temporary event files remain available to the worker and are released on completion, failure, or cancellation. Replacing or removing a profile cancels its owned work; runtime shutdown also reclaims it.

## The work loop's read-only boundary and delegation

`btw.work_loop.read_only` defaults to `true`. With it on, the work loop's tool catalog keeps only reading and searching: `astrbot_file_read_tool`, `astrbot_grep_tool`, web search, memory, and knowledge-base tools stay available, while Shell, Python, file writing and editing, upload and download, browser, CUA, and MCP tools whose `readOnlyHint` is not true are removed. `delegate_coding_task` is then the only way to write. The decision is made by meaning rather than by name: a tool that declares no `required_actions` counts as a writer, plugin tools included, because nothing vouches for it. The setting only removes capabilities: file reading still requires `btw.work_loop.computer_use_runtime` to grant local or sandbox, and roles, path restrictions, sandboxing, WebChat step-up, and the per-capability loop assignments are unchanged. Turning `read_only` off restores the previous write capabilities.

`btw.work_loop.coding_agents` names the local CLI agents a task can be delegated to, and is configured on the Dashboard's **More Features → BTW Dual Loop** page. Each entry carries `id`, `type` (`claude_code`, `codex`, or `custom`), `command`, `model`, `max_output_chars`, `permission_mode` (the Claude Code permission mode, `acceptEdits` by default), `sandbox` (the Codex sandbox, `workspace-write` by default), `project_dir`, `extra_args`, `env`, `timeout_seconds`, and `providers`. `permission_mode` and `sandbox` are policies the CLI itself enforces, not operating-system isolation: the defaults keep an agent writing inside its task folder, a configured `project_dir` is added to what it may write, and `bypassPermissions` and `danger-full-access` must be configured explicitly. Claude Code runs non-interactively under `-p`, so there is no terminal to answer a permission prompt, and `acceptEdits` approves edits alone: a task that runs shell commands -- a test suite, a git command -- waits until `timeout_seconds` expires, and such a task has to choose `bypassPermissions` deliberately. A delegation starts a local process that writes to the filesystem, so `delegate_coding_task` is authorized as `tool.local_exec` and `tool.file_write`: this work loop's Computer Use runtime must be `local`. Allowing it under `sandbox` would be the way out of the sandbox rather than a use of it -- the process is started by AstrBot directly and is not inside the sandbox -- and `inherit` resolves to `none` before the request is built, so neither selects. The `none` default of `provider_settings.computer_use_runtime` turns off file reading and delegation together, and surface elevation such as WebChat step-up and the per-capability loop assignments still apply.

The work loop delegates a write task through `delegate_coding_task`: the task text is written to `<btw.work_loop.workspace_root>/<session id>-<agent id>-<run id>/TASK.md`, and an empty `workspace_root` uses `btw/workspaces` inside the data directory. Every delegation creates a folder of its own, so two delegations in one session cannot overwrite each other. The agent runs in that folder, with its full output logged to `output.log` beside the task. When the run ends, the work loop reads back the status, exit code, artifact paths, and the agent's own final message. Artifacts are the difference the run made: the changed paths from `git status --porcelain` plus anything the run committed in a git work tree, and the files written after the run started in a plain folder. The report names them relative to the workspace root, so it never spells out where AstrBot keeps its data on the host, and caps them at 50 entries. Whatever a stopped run left in its process group or Job Object is ended with it, whether the run timed out, was cancelled, or finished on its own, so a delegation leaves no process still writing.

Each agent may also carry a `providers` list of presets and an `active_provider`. The Dashboard no longer edits them -- a CLI's provider is switched on the **More Features → Third-party Agent Config** page, which rewrites the CLI's own configuration -- but a preset written into the config file by hand still takes effect as described below. A preset's `base_url` and `model` are written into that CLI's own config layer: Claude Code through `--settings` pointing at a settings file in the data directory, and Codex through `--profile astrbot-btw-<agent id>` layering `$CODEX_HOME/astrbot-btw-<agent id>.config.toml`. Each agent gets a layer of its own, so two agents running at once cannot overwrite each other's provider. The credential is never written to disk; it is passed in the child's environment for the length of the run, which Claude Code reads as `ANTHROPIC_AUTH_TOKEN` and which Codex names through the layer's `env_key`, a variable named for the agent. Switching providers therefore never rewrites the user's global CLI configuration, and only the endpoint and model persist. A preset with neither `base_url` nor `api_key` counts as an official login: no layer is written and the agent keeps the user's own session.

The same page keeps `btw.cli_providers`, which is a different list: one provider list per CLI, switched by hand. **Switch** writes the selected provider into that CLI's own global configuration on this host -- Claude Code's `env` block in `~/.claude/settings.json`, and for Codex a managed block at the top of `~/.codex/config.toml` with the credential in `~/.codex/auth.json`. The file is backed up once before the first write, and **Take back** restores that copy and drops the credentials AstrBot stored. When an agent carries no `providers` preset of its own, a delegated run reads this same file: switching a provider here changes the provider a task runs against, as well as your own sessions. Because a switch rewrites a file AstrBot does not own, it is authorized as `coding_cli.config.write` and asks for step-up.

When a task finishes, `btw.work_loop.report_via_conversation` (default `true`) hands the result to the conversation loop, which composes one report: the agent's answer first, then the completion status and the artifact paths. Streamed chunks are unaffected; only the final result carries the report, and one run carries it exactly once. Turning the setting off delivers results from the work loop directly.

## Switching a coding CLI's own global configuration

`btw.cli_providers` is the provider list edited at **More Features → CLI Global Config** (`/cli-config`). It is ordinary configuration: the entries are saved with the profile, and so is `api_key`, like any other provider credential. Each entry carries `id`, `name`, an optional `cli` (`claude_code` or `codex`; empty means either CLI may use it, while an entry added in the Dashboard always names the section it came from), `base_url`, `model`, `note`, and `api_key`. The `id` is unique across the whole list.

A delegated task is not affected by a switch made here: a run loads a configuration layer of its own and does not read these files. What is switched is the CLI's own configuration on this host, which is what the sessions you start by hand read.

This is the one place AstrBot writes outside its own data directory. The target file is backed up once before the first write (`.astrbot-backup`, which "take back" restores), the write is atomic (`mkstemp` + `fsync` + `os.replace` + a directory fsync), a file holding a credential is `0o600`, and a response reports whether a key is stored and never its value. Claude Code is written through the `env` block of `~/.claude/settings.json` (`ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`, `ANTHROPIC_AUTH_TOKEN`), merged key by key with everything else left as it was. The standard library reads TOML but cannot write it, and rewriting a file we cannot parse faithfully would drop the user's comments, so Codex's keys go in a comment-delimited section at the top of `~/.codex/config.toml` (TOML requires top-level keys to precede every table) with the rest left byte for byte as it was; the credential goes in `auth.json`.

Two files are refused rather than replaced: a `settings.json` that exists and cannot be read as a JSON object (JSONC comments, an array), and a Codex section that opens without closing -- where it was meant to end is not knowable, and a guess would leave the file one block longer on every switch. The state route requires `platform.read`; switching and taking the configuration back require the high-risk `coding_cli.config.write`, and therefore a step-up.

## WebUI and authentication

Important `dashboard` defaults:

| Key                      | Default          | Meaning                                                                                                                          |
| ------------------------ | ---------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `enable`                 | `true`           | Enable the WebUI/API.                                                                                                            |
| `username`               | `astrbot`        | Initial username.                                                                                                                |
| `host`                   | `127.0.0.1`      | Listen on loopback only. Remote access requires an explicit `0.0.0.0` or interface binding plus firewall/reverse-proxy controls. |
| `port`                   | `6185`           | HTTP(S) listening port.                                                                                                          |
| `trust_proxy_headers`    | `false`          | Trust `X-Forwarded-For` / `X-Real-IP` only behind a controlled reverse proxy.                                                    |
| `auth_rate_limit.enable` | `true`           | Rate-limit login, TOTP, and other authentication endpoints.                                                                      |
| `totp.*`                 | Managed by WebUI | Dashboard TOTP snapshot retained for configuration export; it is not the authority for account authentication.                   |
| `ssl.enable`             | `false`          | Terminate TLS in AstrBot using the certificate, key, and optional CA path fields.                                                |

Passwords are stored as PBKDF2 hashes in `pbkdf2_password`. New writes leave `password` empty. Existing MD5 values in `password` are still accepted until the next password change. Never write plaintext into either field or manually exchange hashes. To recover access, run:

```bash
uv run astrbot run --reset-password
```

The source entry point also accepts `uv run main.py --reset-password`. Startup logs print the new temporary password and require it to be changed after login.

Dashboard accounts have stable `account_id` values. Their TOTP secret, recovery-code hash, and trusted devices are stored per account. The Security page synchronizes the `dashboard.totp` snapshot for configuration export and UI use, but login and high-risk operations validate only the account record. Do not edit that snapshot manually, copy TOTP fields between accounts, or treat it as a recovery-code bypass.

## System, logging, and response decoration

- `t2i` and `t2i_word_threshold` render long **output results** as images. `t2i_active_template` is maintained by the template manager.
- `t2i_use_file_service` publishes rendered output through a file-token URL and requires a correct `callback_api_base`.
- `http_proxy` / `no_proxy` are the global outbound proxy and bypass list. They are no longer exported as process `HTTP_PROXY`.
- Telegram applies this explicit route to both Bot API requests and `getUpdates` long polling. When no proxy applies, both clients connect directly without inheriting process proxy variables.
- Providers and platforms use three-state `proxy_mode`: `inherit` follows the global config, `direct` disables environment proxies, and `custom` uses only that item's `proxy_url`. An empty string no longer means both inherit and direct.
- No GitHub mirrors are provided by default. Plugin `download_url` values and prefix mirrors must be public HTTPS origins; private and non-HTTPS targets are rejected.
- `platform_settings.segmented_reply` remains a UX feature and stays off by default. Telegram, Discord, and WeCom hard-limit splitting is handled by the send path.
- `log_level` and `log_file_*` control the console Loguru sink, the root logger, plugin loggers without an override, and rotating file logs. `log_level` applies to terminal output, not only the file sink. File logs use the same redacting sink: recognized secret fields, Bearer tokens, URLs, and absolute paths are replaced before write. Cookies, private chat, and custom secrets are not guaranteed; review logs before sharing.
- `trace_enable` is the Trace collection switch; `trace_log_*` controls its separate rotating file.
- `temp_dir_max_size` limits `data/temp` in MiB and defaults to `1024`; a background task removes older files when the limit is exceeded.
- `timezone` is an IANA timezone and defaults to `Asia/Shanghai`.
- `callback_api_base` is the externally reachable base used to build callback and file URLs. It does not change the listening address.
- `plugin_set` limits plugins for the profile; `["*"]` means all and an empty list means none.
- `disable_metrics` disables metric collection. Enable or disable built-in commands individually from Dashboard command management.

## Process-level environment overrides

Only a small set of startup values have environment overrides. There is no general configuration-key-to-environment-variable mapping.

| Environment variable                                                                                     | Purpose                                                                                                          |
| -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `ASTRBOT_ROOT`                                                                                           | Relocate the runtime root.                                                                                       |
| `DASHBOARD_HOST` / `ASTRBOT_DASHBOARD_HOST`                                                              | Override the WebUI bind address.                                                                                 |
| `DASHBOARD_PORT` / `ASTRBOT_DASHBOARD_PORT`                                                              | Override the WebUI port.                                                                                         |
| `DASHBOARD_SSL_ENABLE` / `ASTRBOT_DASHBOARD_SSL_ENABLE`                                                  | Override direct WebUI TLS.                                                                                       |
| `DASHBOARD_SSL_CERT`, `DASHBOARD_SSL_KEY`, `DASHBOARD_SSL_CA_CERTS`, and their `ASTRBOT_`-prefixed forms | Override TLS files.                                                                                              |
| `ASTRBOT_DASHBOARD_INITIAL_PASSWORD`                                                                     | Supply the initial password during first initialization or an explicit reset; password validation still applies. |

Publishing container port `6185` does not override loopback binding. Set the host as well; see [Docker Deployment](../deploy/astrbot/docker).

## Configuration change checklist

1. Confirm that the key exists in the current `DEFAULT_CONFIG` and WebUI metadata.
2. Change it in the WebUI, or stop AstrBot before editing strict JSON.
3. Never expose credentials, TOTP secrets, JWT secrets, or access tokens in issues, logs, or diffs.
4. After restart, inspect logs for removed fields, Provider load failures, or adapter reload failures.
5. Retest network boundaries after changing binding, proxy headers, TLS, Computer Use, MCP, or callback URLs.
6. Validate the default Provider, Persona, plugin pool, and message-session bindings for every profile; the default profile does not automatically represent all profiles.

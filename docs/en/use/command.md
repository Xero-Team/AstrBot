# Built-in Commands

AstrBot commands are registered through the plugin system. Built-in commands now follow a consistent CLI convention: a singular noun root command, a full-word verb subcommand, and long options. Examples include `/plugin list`, `/conversation create`, and `/provider set llm 1`. Former short names such as `/plugin ls`, `/op`, `/reset`, and `/flow on` are not aliases and do not match. `/help` lists currently enabled declared names, or names after an explicit Dashboard rename.

Use `/help` to show enabled root commands and their first-level subcommands. Use `/help --image` or `/help -i` for image-formatted help. If the wake prefix changes, replace `/` in every example with the configured prefix.

## Orbit Command Argument Syntax

AstrBot uses **Orbit Command Syntax** for arguments of registered commands. Orbit is not a shell and never executes a shell. Strict argument parsing starts only after a complete command, command group, or alias matches; a completely unknown root command can still reach ordinary plugin filters or the LLM.

Orbit supports a deterministic subset of POSIX quoting and escaping:

- Only ASCII spaces and tabs separate arguments.
- Everything inside single quotes is literal.
- Inside double quotes, backslash escapes only `$`, backtick, backslash, double quote, and newline. Other backslashes are preserved.
- An unquoted backslash escapes the next character; backslash-newline performs line continuation.
- Adjacent quoted and unquoted fragments form one argument, so `ab"cd"'ef'` becomes `abcdef`.
- `""` and `''` each produce an empty argument. Unicode is preserved, and command matching is case-sensitive.

Orbit performs no parameter, command, arithmetic, or tilde expansion and no globbing, redirection, pipelines, lists, or subshells. Any unescaped `$` or backtick outside single quotes, plus an unquoted word-initial `~`, `*`, `?`, `[`, `|`, `&`, `;`, `<`, `>`, `(`, `)`, word-initial `#`, or newline produces a structured syntax error.

Quote or escape these characters when they are data:

```text
/session name '$HOME'
/session name "a|b"
/session name \*.txt
/session name "C:\Users\bot"
/session name '^user#[0-9]+$'
/plugin install 'https://example.com?a=1&b=2#readme'
```

Declared options can appear before or after positional arguments and support `--name=value`. `--` stops option parsing; for example, `/session name -- -x` passes `-x` as data. Negative numeric positionals such as `-1` do not require the terminator.

## Command and LLM routing

Commands are framed by the profile's `command_prefixes` (default `["/"]`) and matched against the enabled command catalog. Command matching happens before LLM access: a matched command always wins, a bare command group shows its help, and an unknown subcommand returns an Orbit diagnostic instead of becoming an LLM prompt. Non-command messages follow the profile's `llm_access` policy. Its prefixes are complete user-typed strings; they are not automatically combined with `command_prefixes`. When a group message reaches the LLM is in [When the bot replies in groups](./group-wake).

Enabled command paths, aliases, descendants, and non-empty LLM prefix roots share one scoped namespace. A conflict is rejected or excluded from the runtime catalog until Dashboard rename leaves one owner, or the command-update API records a takeover. Dashboard highlights conflicts and exposes rename; it does not offer a takeover button. The built-in LLM state commands are `/llm status`, `/llm enable`, and `/llm disable`; `/chat` is not their compatibility alias.

## Command Reference

### Help

- `/help`: Show enabled root commands, first-level subcommands, and version information.
- `/help --image` or `/help -i`: Generate image-formatted help.

### Bot Presence

- `/bot status [this|UMO]`: Show the version, session, LLM, and TTS switches for the target session. Omit the argument or use `this` for the current session; an explicit UMO requires `instance_operator` or above.
- `/bot enable [this|UMO]`: Enable the target session. Omit the argument or use `this` for the current session; an explicit UMO requires `instance_operator` or above.
- `/bot disable [this|UMO]`: Disable the target session. Omit the argument or use `this` for the current session; an explicit UMO requires `instance_operator` or above.
- `/bot leave`: Prompt for leave confirmation. Requires `session.manage` and only works in group chats.
- `/bot leave --confirm` or `/bot leave -c`: Leave the current group after confirmation. Rejected when the platform does not declare `leave_group`.

Both `enable` and `disable` are idempotent. They write the existing `session_enabled` flag for the target UMO, same scope as `/llm`. When the session is disabled, the pipeline stops ordinary events but still allows `/bot status` and `/bot enable` so the session can be turned back on from chat. `/bot status` also reports the full-block state. `/session block [this|UMO]` and `/session unblock [this|UMO]` require `instance_operator` or above and fully block or restore all functionality for the target session; a fully blocked session only allows `/bot status` and `/session unblock`. A bare `/bot` only shows the subcommand tree.

### Session Information

- `/session info [this|UMO]`: Show the UMO, user ID, authorization subject (`im:{platform}:{bot}:{sender}`), platform ID, message type, and session ID. Omit the argument or use `this` for the current session; an explicit UMO requires `instance_operator` or above and shows that session's auto name and alias.
- `/session name [--target UMO]`: Show the auto name and saved alias; requires `session.manage`. `--target` requires `instance_operator` or above.
- `/session name [--target UMO] <name>`: Set the display alias; requires `session.manage`. `GreedyStr` allows spaces.
- `/session name [--target UMO] --clear`: Clear the display alias.

After the waking stage finalizes `is_wake`, the automatic name is written to storage. A manual alias takes priority; automatic upserts do not overwrite `user_alias`.

The user ID from `/session info` can be granted current-session `session_admin` with `/admin grant`. That is not a global operator. With group `unique_session` enabled, the command also reports the group ID used for allowlists.

### Cross-session watches and sending

- `/session watch [listener|this] <target> [seconds]`: Forward subsequent incoming messages from the target into the listener session; requires `session.watch`. Omit the listener or write `this` for the current session. Duration is 1–864000 seconds (up to 10 days), default 43200 seconds (12 hours), measured on the wall clock. When it expires, the listener session receives an end notice.
- `/session watches [listener|this]`: List watches you created and their remaining time. Omit the argument or write `this` for the current session as the listener.
- `/session unwatch [listener|this] <target>`: Stop a matching watch that you own. Omit the listener or write `this` for the current session.
- `/session connect <UMO>`: Link the current session to the target without expiry; requires `session.watch`. Incoming messages from the target are forwarded until `/session disconnect` or `/session unlink`. One link per actor and listener; connecting again replaces the previous target. `/session connect` with no argument shows the current link. Extra tokens such as a duration are rejected.
- `/session disconnect`: Drop the unbounded link in the current session; requires `session.read`.
- `/session pair <UMO>`: Create two unbounded directed edges between the current session and the target; requires `session.watch`. Both adapters must already be loaded and able to send proactively. Only human messages are forwarded; the Bot's own speech and delivery echoes are skipped to prevent loops. The far side sees the **destination Bot account** speaking, with the same localized source header as a watch (sender name and source platform). This does not forge the source sender's platform identity and does not inject into the target inbound pipeline. It does not bind `/send`; `/send` without a UMO still uses `connect` only. Extra tokens such as a duration are rejected. Limit is 8 pairs (16 `pair` edges) per actor, alongside 16 connects, and it does not consume the watch quota. Pairing the same endpoints again keeps the existing `pair_id` and both `rule_id` values. Pairing over an existing watch or connect replaces those two directions for this actor. Already stored headerless pairs stay as they are; `unpair` and `pair` again to pick up the source header.
- `/session unpair [UMO]`: Delete both edges that share a `pair_id`; requires `session.read`. Omit the UMO only when this actor has exactly one pair that includes the current session; zero pairs reports none; more than one pair requires the other UMO.
- `/session links`: List visible watches, connects, and pairs with `rule_id`, kind, and remaining time or no expiry; pairs also show `pair_id`. Permission matches `watches` (`session.read`). Creators see only their own rules. An `instance_operator` on the current session configuration also sees rules whose source or target config id equals that configuration. `operator` / `root` see all rules.
- `/session unlink <rule_id>`: Remove a watch or connect by its 12-character lowercase hex id. Creators can remove their own rules after their role is revoked. An `instance_operator` on the current configuration can remove a rule whose either config id belongs to that configuration; `operator` / `root` can remove any rule. If the target is `kind=pair`, the command is refused and both edges remain; use `unpair`.
- `/session filter <rule_id>`: Show the match/except filter on one directed edge. Permission matches `links` (`session.read` plus the operator extra scope).
- `/session filter <rule_id> match|except subject|role|text <value>`: Append one filter value to that edge. The same dimension is OR; dimensions AND; an except hit drops the message. `text` takes the rest of the line as a Python `re.search` pattern (at most 256 characters, Unicode and case-sensitive unless the pattern uses `(?i)`). Invalid patterns are rejected at save time. `role` is an AstrBot authorization role on the **source session** (`guest` / `member` / `session_admin` / `session_owner` / `instance_operator` / `operator` / `root`), not a platform group role. A lookup miss is `guest`. Each dimension accepts at most 16 values. Creators can change their own edges after their role is revoked, with the same extra operator scope as `unlink`. Pair edges can be filtered independently; unpair still removes both.
- `/session filter <rule_id> clear [match|except|all]`: Clear one side or both. Omitting the side equals `all`. Clearing removes the whole side; to change one subject, clear and add again.
- `/send <UMO> [content]`: Send text and attachments from the same message through the target Bot account; requires `session.send`. An attachment-only body is allowed. This does not register a `reply` command.
- `/send [content]`: After `/session connect`, send to the linked target without repeating the UMO. Attachment-only bodies are allowed. `pair` is not a default `/send` target.

Watching, connecting, pairing, and sending require the current identity to hold `instance_operator` permission in the configuration shared by both sessions. Group admin or private-session ownership does not grant this access. Forwarded content is visible to everyone in the receiving session. Watches, links, and pairs forward new incoming messages only, without reading history. Empty match and except filters forward every human message. `watch` / `connect` / `pair` do not accept filter flags; set filters afterwards with `/session filter`. Subject filters rebuild `Subject.im` from the source route platform id, the source adapter `self_id`, and `SenderSnapshot.id`. Text filters concatenate `PortablePart` string values and ignore media and `NativeContent`; a media-only body fails `match.text` and does not trip `except.text`. Rules are stored in SQLite, so unexpired watches, all connects, and all pairs survive process restart; expired watches are cleared at startup or when they elapse, and the listener is notified. Limits remain 16 watches, 16 links, and 8 pairs per actor. Authorization is checked again for each forwarded message, so revocation stops delivery. Running `/session watch` again on the same endpoints keeps the `rule_id` and resets the duration. A watch and a connect on the same direction replace each other. If either target direction is already a pair, `watch` / `connect` is refused and asks for `unpair` first; the pair is not split.

Text and media retain their message-chain order; targets without mixed-content delivery receive separate messages. Cross-platform mentions become text. Quotes use accepted-message ID mappings when available and otherwise become a quote summary. Unavailable attachments and unsupported native content leave text placeholders. Platform cards, private syntax, and mini apps cannot be guaranteed to reproduce on another platform. When the source is an expanded merged forward and the target declares `forward`, the far side sees a merged-forward card: node authors are the original node `uin` / `name`, and the speaking account is still the destination Bot. Targets that do not support it still receive the labeled transcript.

`send` arguments still follow the Orbit syntax above. Its body is taken from the original message chain after removing the command header, preserving original text and attachment positions. Results distinguish platform acceptance, partial acceptance, rejection, and unknown status. Acceptance does not imply a read receipt. Check the target session before retrying partial or unknown submissions.

Targets such as LINE that require public media URLs need a reachable HTTPS `callback_api_base`. Forwarded media uses expiring file-token copies; private file IDs from the source Bot are not passed to another platform. The WeChat Official Account adapter currently cannot receive proactive sends. Other adapters may depend on account mode, a push Webhook, target-session state, or server permissions.

This stage has no Dashboard management surface. Create, list, and stop watches, and send across sessions, only through the IM commands above. The command-management page can enable or disable those commands, but it cannot list or operate watches. The same commands work in WebChat like any other IM session.

### Conversations

- `/conversation create`: Create and switch to a new conversation.
- `/conversation reset`: Clear the current context, corresponding third-party Agent Runner state, and this session's [group chat context awareness](./group-chat-context) in-memory cache.
- `/conversation stats`: Show input, cached-input, and output token statistics.
- `/conversation history [--page N|-p N]`: Show conversation history.
- `/conversation list [--page N|-p N]`: List conversations.
- `/conversation switch <index>`: Switch to a listed conversation.
- `/conversation rename <new-title>`: Rename the current conversation; spaces are accepted.
- `/conversation delete`: Delete the current conversation.
- `/conversation create-for <session-id>`: Create a conversation for another group session; requires `session.assign` and `session.manage`.

`reset`, `delete`, `create`, `switch`, and `rename` always declare `session.manage`. A private-chat peer is the current-session owner, so `/conversation reset` and other `session.manage` builtins work in that DM. Groups still need `session_admin` or above. Dashboard command permissions take precedence over defaults.

### Running Tasks

- `/work <task>`: Submit the remaining text to the BTW work loop without a `/chat` prefix or automatic classification. Requires `session.read`, with `btw.enabled` and `btw.work_loop.enabled` enabled on the current profile. The command identity is `builtin_commands:work`. Command quoting rules still apply.
- `/work` or `/work status`: Show the latest task's text and status for the current profile and session: queued, running, completed, failed, cancelled, or delivery unconfirmed. `delivery unconfirmed` means the task itself finished but the platform never confirmed accepting its result. `status` queries only when it is the entire remainder, ignoring case; `/work status refactor` submits a task. Requires `session.read`. State is kept in memory, cleared on restart or profile reload/removal, and terminal tasks expire after `btw.work_session.max_age_seconds` (default 3600).
- `/task stop`: Request that running Agent or third-party Agent Runner tasks in the current session stop, without deleting history. The local run stops consuming the runner and is recorded as cancelled. This ends the local wait only; a task already accepted by a third-party service is not revoked remotely.

### Providers and Models

- `/provider list`: List LLM, TTS, and STT Providers, the current selections, and reachability status.
- `/provider set llm <index>`: Select an LLM Provider.
- `/provider set tts <index>`: Select a TTS Provider.
- `/provider set stt <index>`: Select an STT Provider.
- `/model list`: List models available from the current LLM Provider.
- `/model set <name-or-index>`: Select a model; a name can also resolve to another configured Provider.

These commands require `provider.use`. Cross-session assignment also requires `session.assign`.

### Session Variables

- `/variable set <key> <value>`: Set an Agent Runner input variable.
- `/variable unset <key>`: Remove an input variable.

### LLM Chat State

- `/llm status`: Show whether LLM chat is enabled for the current session.
- `/llm enable`: Enable LLM chat for the current session.
- `/llm disable`: Disable LLM chat for the current session.

These commands require `session.manage`. Both `enable` and `disable` are idempotent. `/llm` only controls whether the LLM is enabled; it does not change streaming mode.

### TTS state

- `/tts status`: Show whether TTS is enabled for the current session.
- `/tts enable`: Enable TTS for the current session.
- `/tts disable`: Disable TTS for the current session.

These commands require `session.manage`. Both `enable` and `disable` are idempotent. `/bot status` shows the session, LLM, and TTS switches together.

### Session streaming

- `/flow enable`: Force streaming for the current session.
- `/flow disable`: Force non-streaming for the current session.
- `/flow unset`: Remove the session override and follow global `provider_settings.streaming_response`.
- `/flow status`: Show the override and effective mode.

These commands require `session.manage`. There is no argument-less toggle.

### Session administrators

- `/admin list`: List role bindings visible in the current session.
- `/admin grant <user-id>`: Grant `session_admin` for the current session, not a global operator.
- `/admin revoke <user-id>`: Revoke `session_admin` for the current session.

All three subcommands require `identity.manage`. A current session owner may manage `session_admin` and `member` in that session only and cannot delegate ownership. See [Authorization](./authorization) for the role model.

### Personas

- `/persona status`: Show the default Persona and the Persona effectively used by the current conversation.
- `/persona list`: List Personas.
- `/persona show <persona_id>`: Show a Persona's system prompt.
- `/persona set <persona_id>`: Select a Persona for the current conversation.
- `/persona unset`: Explicitly select no Persona for the current conversation.

Persona subcommands require `agent.manage`. Entering `/persona` alone displays the subcommand tree.

### Plugins

- `/plugin list`: List loaded plugins.
- `/plugin show <plugin-name>`: Show plugin version, author, and registered commands.
- `/plugin enable <plugin-name>`: Enable a plugin; requires `extension.manage`.
- `/plugin disable <plugin-name>`: Disable a plugin; requires `extension.manage`.
- `/plugin install <repository-url>`: Install a plugin; requires `extension.plugin_install` and Dashboard step-up.

Plugin load, unload, reload, enable, and disable operations immediately rebuild the command catalog and refresh enabled Telegram/Discord native command surfaces.

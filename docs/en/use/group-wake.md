# When the bot replies in groups

If the bot ignores a group message, the model is usually fine. The active configuration profile's LLM access policy did not admit that message.

This page only covers **whether a message is sent to the built-in AI**. Injecting recent group messages into the next request is [Group Chat Context Awareness](./group-chat-context).

Open **Config → Platform → General**. These fields belong to the current profile. Editing `default` does not change a group bound to another profile. See [Configuration profiles](./config-profiles).

## Defaults

| Scene          | Default                           | Effect                                 |
| -------------- | --------------------------------- | -------------------------------------- |
| Direct message | `llm_access.private = prefix`     | Requires an LLM prefix                 |
| Group          | `llm_access.group = prefix`       | Requires an LLM prefix                 |
| LLM prefix     | `llm_access.prefixes = ["/"]`     | `/hello` is handled; `hello` is not    |
| Reply to bot   | `llm_access.reply_to_bot = false` | Replying does not extra-admit the turn |

After a default install, both IM direct messages and groups need an LLM prefix. `open` remains a legal opt-in. Sending from Dashboard WebChat is an explicit aim at the built-in AI and does not need a prefix.

`@`, `Mention`, and `MentionAll` are message-chain markers. Their presence does not change the built-in LLM gate. Saved `mention` / `prefix_or_mention` values are treated as `prefix` at runtime and are not rewritten on disk.

## Command prefixes and LLM prefixes are separate

| Field                 | Dashboard label      | Role                                                                  |
| --------------------- | -------------------- | --------------------------------------------------------------------- |
| `command_prefixes`    | Command prefixes     | Frames command headers only. Default `["/"]`                          |
| `llm_access.prefixes` | LLM trigger prefixes | Complete strings users type. Never concatenated with command prefixes |

Routing **always matches commands before LLM access**:

1. An enabled command runs as a command. The model is not called.
2. A bare command group (for example `/plugin`) shows subcommand help.
3. An unknown subcommand returns an Orbit diagnostic and is **not** treated as an LLM prompt.
4. Everything else follows `llm_access`, continuation, and the explicit-surface stamp.

Both prefix lists default to `/`. A non-empty LLM prefix occupies that profile's first command root. Dashboard rejects a save that conflicts with an enabled command. See [Built-in commands](./command).

## Group policy

`llm_access.group` values:

| Value    | When the LLM runs                           |
| -------- | ------------------------------------------- |
| `open`   | Every ordinary group message. Easy to flood |
| `prefix` | Default. Message starts with an LLM prefix  |
| `off`    | Do not open a new LLM turn                  |

Two extra conditions:

- **Allow LLM when replying to the bot** (`reply_to_bot`): an additional OR. Even `group=off` can wake on a reply to the bot.
- **Continuation**: later fragments of an open LLM turn window do not need to repeat the prefix.

A message that starts by @-ing **someone else** does not wake on prefix. That keeps talk directed at other people from hitting the bot. The mention itself does not admit the LLM, and `MentionAll` does not extra-admit either.

### Suggested recipes

- Large group, low noise: keep `prefix`.
- Also answer replies: turn on `reply_to_bot`.
- Anyone may chat: set `open` (this raises call volume).

`llm_access.private` is only `open` / `prefix` / `off`. The default is `prefix`. `off` blocks new LLM turns; an in-flight continuation may still continue.

## Explicit surfaces

These inbound paths stamp `explicit_surface`. After a command miss, the built-in LLM is admitted. `private=off` / `group=off` still block a new turn; the stamp does not bypass that kill switch:

- Discord slash commands / interaction follow-up
- Dashboard WebChat sends
- WeCom AI Bot inbound
- Cron jobs
- `PlatformManager.create_event(..., is_wake=True)`
- The follow-up after a prefix-only wait

Discord user mentions and bot-owned role mentions **do not** receive this stamp; they still follow the `llm_access` gate above. WebChat does not inject `/` into `message_str`: `hello` goes to the LLM; a user-typed `/help` still matches commands first.

## Continuations

If the session already has an open LLM turn window (inbound coalesce waiting for the rest of a sentence, or a turn still running), later fragments can continue without repeating the prefix. A real command discards the buffered turn. Inbound coalesce is off by default and currently merges **direct messages only**. See [Platform handling](./platform-settings#inbound-turn-coalescing).

## Prefix-only messages

`empty_mention_waiting` is on by default. A message that is only a command prefix (for example a lone `/`) waits up to 60 seconds for that user's next message and resubmits it with `explicit_surface`, so the follow-up does not need another prefix. Turning the switch off skips the wait. An empty `@` does not start the built-in AI and does not reinsert a `Mention` for resubmit. `off` still blocks a new LLM turn.

## Isolated sessions

**Isolated sessions** (`platform_settings.unique_session`) is off by default: one group shares one conversation. When on, each member gets a separate context.

- Mutually exclusive with experimental group-sender concurrency.
- Group notice/request events stay on the group session.
- `/session info` also reports the group ID used for allowlists when isolation is on.

Isolation changes **who owns the context**. It does not relax `llm_access.group`.

## Still dropped after a wake

Pipeline order: wake check → [allowlist](./platform-settings#allowlist) → session enabled → coalesce → rate limit → content safety → preprocess → plugin or LLM.

A policy admit can still vanish behind an allowlist, a custom rule that disabled the session, rate limits, or content safety. Session on/off is in [Custom rules](./custom-rules). Unmatched ordinary text still reaches plugin `EventMessageType.ALL` / `PRIVATE_MESSAGE` listeners.

## Common misconfigurations

1. Talking plainly in a group or DM while the policy is still the default `prefix`.
2. Changing `command_prefixes` and expecting the LLM prefix to follow.
3. Editing `default` while the group is bound to another profile. Check the UMO with `/session info`.
4. Assuming @-ing the bot starts the built-in AI. Mentions are message-chain markers.
5. Assuming a reply equals a mention; `reply_to_bot` is a separate switch.
6. Allowlist enabled with a non-empty list that omits this group.
7. A custom rule or `/llm disable` turned LLM off for the session.
